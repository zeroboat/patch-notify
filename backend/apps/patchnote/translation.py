"""
Ollama 내부 AI 서버를 이용한 패치노트 영문 번역 모듈

- 패치노트 등록 직후 백그라운드 스레드에서 실행
- Feature / Improvement / BugFix / Remark / Internal 5개 섹션을 단일 JSON 배치 호출로 번역
- 긴 섹션(_CHUNK_THRESHOLD 초과)은 배치 제외 후 최상위 <li> 단위 청킹 번역
- 키 불일치 시 1회 재시도, 재시도도 실패하면 섹션별 개별 호출로 폴백
- Ollama 서버가 없거나 응답 실패 시 조용히 건너뜀 (서비스 영향 없음)
"""

import json
import logging
import re
import threading

import requests

logger = logging.getLogger(__name__)

_KEY_DESCRIPTIONS = {
    "features":     "신규 기능 (New Features)",
    "improvements": "개선 사항 (Improvements)",
    "bugfixes":     "버그 수정 (Bug Fixes)",
    "remarks":      "비고 / 운영자 공지 (Remarks)",
    "internals":    "내부 메모 / 사내 전달 사항 (Internal Notes)",
}

_BATCH_PROMPT_TEMPLATE = (
    "아래는 JSON 형식으로 제공된 HTML 텍스트들이야. "
    "각 HTML의 한글 텍스트만 영어로 번역하되, HTML 태그와 속성은 수정하지 말고 원문 그대로 유지해줘. "
    "응답은 반드시 입력과 동일한 키를 가진 JSON 형식으로만 반환해. 키를 바꾸거나 누락하면 안 돼. 코드블록이나 다른 설명은 필요 없어.\n\n"
    "각 키의 의미:\n{key_descriptions}\n\n"
    "{json_input}"
)

_SINGLE_PROMPT_TEMPLATE = (
    "아래는 HTML 텍스트야 ({section_desc}). "
    "한글 텍스트만 영어로 번역하되, HTML 태그와 속성은 수정하지 말고 원문 그대로 유지해줘. "
    "번역된 HTML만 반환해. 다른 설명은 필요 없어.\n\n"
    "{html_input}"
)

# 이 값을 초과하는 섹션은 배치에서 제외하고 청킹 번역으로 처리
_CHUNK_THRESHOLD = 2500

# GTX 1660(VRAM 6GB) 기준 8192로 설정 시 0.6 GB가 CPU/RAM으로 내려가지만 허용 가능한 수준
_NUM_CTX = 8192

# num_ctx=8192 기준 응답 시간이 늘어나므로 기존 120초에서 상향
_OLLAMA_TIMEOUT = 240


def _extract_json(text: str) -> dict | None:
    """응답 텍스트에서 JSON 객체 추출"""
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _validate_keys(requested: dict, result: dict) -> bool:
    """번역 결과 키가 요청 키와 완전히 일치하는지 확인"""
    return set(requested.keys()) == set(result.keys())


def _get_ollama_config():
    from apps.config.models import SiteConfig
    cfg = SiteConfig.get()
    if not cfg.ollama_host or not cfg.ollama_model:
        return None, None
    return cfg.ollama_host, cfg.ollama_model


def _extract_top_li_items(body: str) -> list[str]:
    """HTML body에서 최상위 <li>...</li> 항목 추출 (중첩 ul/ol은 깊이 추적으로 건너뜀)"""
    tag_re = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)
    items = []
    depth = 0
    item_start = -1
    i = 0

    while i < len(body):
        m = tag_re.match(body, i)
        if not m:
            i += 1
            continue

        is_close = m.group(1) == '/'
        tag_name = m.group(2).lower()

        if tag_name == 'li':
            if not is_close and depth == 0:
                item_start = i
            elif is_close and depth == 0 and item_start >= 0:
                items.append(body[item_start:m.end()])
                item_start = -1
        elif tag_name in ('ul', 'ol'):
            if not is_close:
                depth += 1
            elif depth > 0:
                depth -= 1

        i = m.end()

    return items


def _chunk_html_content(html: str) -> list[str]:
    """
    긴 HTML을 최상위 <li> 경계에서 _CHUNK_THRESHOLD 이하 청크로 분할.
    임계값 이하이거나 구조 파악 불가 시 [html] 반환.
    """
    if len(html) <= _CHUNK_THRESHOLD:
        return [html]

    stripped = html.strip()
    m = re.match(r'^(<(?:ul|ol)[^>]*>)([\s\S]*)(<\/(?:ul|ol)>)$', stripped, re.IGNORECASE)
    if not m:
        return [html]

    open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
    items = _extract_top_li_items(body)
    if len(items) <= 1:
        return [html]

    chunks, current, current_len = [], [], len(open_tag) + len(close_tag)
    for item in items:
        if current and current_len + len(item) > _CHUNK_THRESHOLD:
            chunks.append(open_tag + "".join(current) + close_tag)
            current, current_len = [item], len(open_tag) + len(close_tag) + len(item)
        else:
            current.append(item)
            current_len += len(item)
    if current:
        chunks.append(open_tag + "".join(current) + close_tag)

    return chunks if len(chunks) > 1 else [html]


def _call_ollama_batch(sections: dict[str, str], attempt: int = 1) -> dict[str, str]:
    """
    여러 HTML 섹션을 JSON으로 묶어 단일 Ollama 호출로 번역.
    키 불일치 시 1회 재시도, 재시도도 실패하면 빈 dict 반환.
    """
    host, model = _get_ollama_config()
    if not host:
        return {}

    key_desc_lines = "\n".join(
        f"  - {k}: {_KEY_DESCRIPTIONS[k]}"
        for k in sections
        if k in _KEY_DESCRIPTIONS
    )
    json_input = json.dumps(sections, ensure_ascii=False, indent=2)
    prompt = _BATCH_PROMPT_TEMPLATE.format(
        key_descriptions=key_desc_lines,
        json_input=json_input,
    )

    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"num_ctx": _NUM_CTX}},
            timeout=_OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        result = _extract_json(raw)

        if result is None:
            logger.warning("Ollama 배치 번역 응답 파싱 실패 (시도 %d): %s", attempt, raw[:200])
            return {}

        if not _validate_keys(sections, result):
            logger.warning(
                "Ollama 배치 번역 키 불일치 (시도 %d): 요청=%s 응답=%s",
                attempt, sorted(sections.keys()), sorted(result.keys()),
            )
            if attempt < 2:
                logger.info("배치 번역 재시도 중...")
                return _call_ollama_batch(sections, attempt=2)
            return {}

        return result

    except Exception as exc:
        logger.warning("Ollama 배치 번역 실패 (시도 %d): %s", attempt, exc)
        return {}


def _translate_chunk(key: str, html: str) -> str | None:
    """HTML 청크 단위 번역 (단일 Ollama 호출)"""
    host, model = _get_ollama_config()
    if not host:
        return None

    desc = _KEY_DESCRIPTIONS.get(key, key)
    prompt = _SINGLE_PROMPT_TEMPLATE.format(section_desc=desc, html_input=html)

    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"num_ctx": _NUM_CTX}},
            timeout=_OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        raw = re.sub(r"```(?:html)?", "", raw).strip()
        return raw if raw else None
    except Exception as exc:
        logger.warning("Ollama 단일 번역 실패 (%s): %s", key, exc)
        return None


def _call_ollama_single(key: str, html: str) -> str | None:
    """단일 섹션 번역 (배치 실패 시 폴백). 긴 내용은 자동 청킹 후 병합."""
    chunks = _chunk_html_content(html)
    if len(chunks) == 1:
        return _translate_chunk(key, html)

    logger.info("섹션 '%s' 청킹 번역 시작 (%d 청크)", key, len(chunks))
    translated_chunks = []
    for chunk in chunks:
        result = _translate_chunk(key, chunk)
        if result is None:
            logger.warning("섹션 '%s' 청크 번역 실패 — 전체 섹션 번역 포기", key)
            return None
        translated_chunks.append(result)

    # 원본 외부 태그 유지하며 청크 병합
    outer = re.match(r'^(<(?:ul|ol)[^>]*>)', html.strip(), re.IGNORECASE)
    tag_open = outer.group(1) if outer else '<ul>'
    tag_name = 'ul' if re.search(r'ul', tag_open, re.IGNORECASE) else 'ol'
    inner_re = re.compile(rf'^<(?:{tag_name})[^>]*>([\s\S]*)<\/{tag_name}>$', re.IGNORECASE)

    inner_parts = []
    for chunk in translated_chunks:
        inner_m = inner_re.match(chunk.strip())
        inner_parts.append(inner_m.group(1) if inner_m else chunk)

    return f"{tag_open}{''.join(inner_parts)}</{tag_name}>"


def _run_translation(patch_note_id: int):
    """백그라운드 스레드 진입점"""
    from .models import PatchNote, Feature, Improvement, BugFix, Remark, Internal

    try:
        patch_note = PatchNote.objects.get(id=patch_note_id)

        section_map = {
            'features':     (Feature,     patch_note.features.filter(content_en__isnull=True).first()),
            'improvements': (Improvement, patch_note.improvements.filter(content_en__isnull=True).first()),
            'bugfixes':     (BugFix,      patch_note.bugfixes.filter(content_en__isnull=True).first()),
            'remarks':      (Remark,      patch_note.remarks.filter(content_en__isnull=True).first()),
            'internals':    (Internal,    patch_note.internals.filter(content_en__isnull=True).first()),
        }

        to_translate = {
            key: obj.content
            for key, (_, obj) in section_map.items()
            if obj is not None
        }

        if not to_translate:
            logger.info("패치노트 %s 번역할 항목 없음", patch_note_id)
            patch_note.translation_status = PatchNote.TRANSLATION_SKIPPED
            patch_note.save(update_fields=["translation_status", "updated_at"])
            return

        patch_note.translation_status = PatchNote.TRANSLATION_TRANSLATING
        patch_note.save(update_fields=["translation_status", "updated_at"])

        # 긴 섹션은 배치에서 제외 — 배치 프롬프트 자체가 컨텍스트 초과하는 것 방지
        to_batch = {k: v for k, v in to_translate.items() if len(v) <= _CHUNK_THRESHOLD}
        to_single = {k: v for k, v in to_translate.items() if len(v) > _CHUNK_THRESHOLD}

        if to_single:
            logger.info(
                "패치노트 %s 긴 섹션 %s → 배치 제외, 개별 청킹 번역",
                patch_note_id, list(to_single.keys()),
            )

        translated = {}

        # 짧은 섹션 배치 번역
        if to_batch:
            batch_result = _call_ollama_batch(to_batch)
            if batch_result:
                translated.update(batch_result)
            else:
                logger.info("패치노트 %s 배치 번역 실패 → 섹션별 개별 호출로 폴백", patch_note_id)
                for key, html in to_batch.items():
                    result = _call_ollama_single(key, html)
                    if result:
                        translated[key] = result

        # 긴 섹션 개별 청킹 번역
        for key, html in to_single.items():
            result = _call_ollama_single(key, html)
            if result:
                translated[key] = result

        if not translated:
            patch_note.translation_status = PatchNote.TRANSLATION_FAILED
            patch_note.save(update_fields=["translation_status", "updated_at"])
            return

        for key, (_, obj) in section_map.items():
            if obj is not None and key in translated and translated[key]:
                obj.content_en = translated[key]
                obj.save(update_fields=["content_en", "updated_at"])

        patch_note.translation_status = PatchNote.TRANSLATION_DONE
        patch_note.save(update_fields=["translation_status", "updated_at"])
        logger.info("패치노트 %s 영문 번역 완료 (섹션: %s)", patch_note_id, list(translated.keys()))

    except PatchNote.DoesNotExist:
        logger.error("번역 대상 패치노트를 찾을 수 없습니다: id=%s", patch_note_id)
    except Exception as exc:
        logger.error("패치노트 %s 번역 중 오류: %s", patch_note_id, exc)
        try:
            PatchNote.objects.filter(id=patch_note_id).update(
                translation_status=PatchNote.TRANSLATION_FAILED
            )
        except Exception:
            pass


def start_translation(patch_note_id: int):
    """패치노트 등록 후 호출 — 데몬 스레드로 번역 시작"""
    thread = threading.Thread(
        target=_run_translation,
        args=(patch_note_id,),
        daemon=True,
        name=f"translate-patchnote-{patch_note_id}",
    )
    thread.start()

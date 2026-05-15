"""
Ollama 내부 AI 서버를 이용한 패치노트 영문 번역 모듈

- 패치노트 등록 직후 백그라운드 스레드에서 실행
- Feature / Improvement / BugFix / Remark / Internal 5개 섹션을 단일 JSON 배치 호출로 번역
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
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
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


def _call_ollama_single(key: str, html: str) -> str | None:
    """단일 섹션 번역 (배치 실패 시 폴백)"""
    host, model = _get_ollama_config()
    if not host:
        return None

    desc = _KEY_DESCRIPTIONS.get(key, key)
    prompt = _SINGLE_PROMPT_TEMPLATE.format(section_desc=desc, html_input=html)

    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        # 코드블록 제거
        raw = re.sub(r"```(?:html)?", "", raw).strip()
        return raw if raw else None
    except Exception as exc:
        logger.warning("Ollama 단일 번역 실패 (%s): %s", key, exc)
        return None


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

        translated = _call_ollama_batch(to_translate)

        # 배치 실패 시 섹션별 개별 호출로 폴백
        if not translated:
            logger.info("패치노트 %s 배치 번역 실패 → 섹션별 개별 호출로 폴백", patch_note_id)
            translated = {}
            for key, html in to_translate.items():
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

"""
Ollama 내부 AI 서버를 이용한 패치노트 영문 번역 모듈

- 패치노트 등록 직후 백그라운드 스레드에서 실행
- Feature / Improvement / BugFix / Remark 4개 섹션을 단일 JSON 배치 호출로 번역
- Ollama 서버가 없거나 응답 실패 시 조용히 건너뜀 (서비스 영향 없음)
"""

import json
import logging
import re
import threading

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_BATCH_PROMPT_TEMPLATE = (
    "아래는 JSON 형식으로 제공된 HTML 텍스트들이야. "
    "각 HTML의 한글 텍스트만 영어로 번역하되, HTML 태그와 속성은 수정하지 말고 원문 그대로 유지해줘. "
    "응답은 반드시 동일한 키를 가진 JSON 형식으로만 반환해. 코드블록이나 다른 설명은 필요 없어.\n\n"
    "{json_input}"
)


def _extract_json(text: str) -> dict | None:
    """응답 텍스트에서 JSON 객체 추출 (코드블록 등 무시)"""
    # ```json ... ``` 또는 ``` ... ``` 코드블록 제거
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 첫 번째 { ... } 블록 추출
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _call_ollama_batch(sections: dict[str, str]) -> dict[str, str]:
    """
    여러 HTML 섹션을 JSON으로 묶어 단일 Ollama 호출로 번역.
    sections: {'features': '<html>', 'improvements': '<html>', ...}
    반환: 동일 키로 번역된 dict. 실패 시 빈 dict.
    """
    json_input = json.dumps(sections, ensure_ascii=False, indent=2)
    try:
        resp = requests.post(
            f"{settings.OLLAMA_HOST}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": _BATCH_PROMPT_TEMPLATE.format(json_input=json_input),
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        result = _extract_json(raw)
        if result is None:
            logger.warning("Ollama 배치 번역 응답 파싱 실패: %s", raw[:200])
            return {}
        return result
    except Exception as exc:
        logger.warning("Ollama 배치 번역 실패: %s", exc)
        return {}


def _run_translation(patch_note_id: int):
    """백그라운드 스레드 진입점 — 4개 섹션을 단일 배치 호출로 번역"""
    from .models import PatchNote, Feature, Improvement, BugFix, Remark

    try:
        patch_note = PatchNote.objects.get(id=patch_note_id)

        # 미번역 항목 수집 (섹션당 최대 1개 레코드)
        section_map = {
            'features':     (Feature,     patch_note.features.filter(content_en__isnull=True).first()),
            'improvements': (Improvement, patch_note.improvements.filter(content_en__isnull=True).first()),
            'bugfixes':     (BugFix,      patch_note.bugfixes.filter(content_en__isnull=True).first()),
            'remarks':      (Remark,      patch_note.remarks.filter(content_en__isnull=True).first()),
        }

        # 실제 내용이 있는 섹션만 번역 대상으로
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

        # 번역 시작
        patch_note.translation_status = PatchNote.TRANSLATION_TRANSLATING
        patch_note.save(update_fields=["translation_status", "updated_at"])

        translated = _call_ollama_batch(to_translate)

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

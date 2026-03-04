"""
Ollama 내부 AI 서버를 이용한 패치노트 영문 번역 모듈

- 패치노트 등록 직후 백그라운드 스레드에서 실행
- Feature / Improvement / BugFix / Remark 항목별 content_en 채움
- Ollama 서버가 없거나 응답 실패 시 조용히 건너뜀 (서비스 영향 없음)
"""

import logging
import threading

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "아래 내용은 HTML 형식이야. HTML 태그와 속성은 수정하지 말고 원문 그대로 유지하면서 한글 텍스트만 영어로 번역해줘.\n\n"
    "{text}"
)


def _call_ollama(text: str) -> str:
    """Ollama /api/generate 호출 → 번역 결과 반환. 실패 시 빈 문자열."""
    try:
        resp = requests.post(
            f"{settings.OLLAMA_HOST}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": _PROMPT_TEMPLATE.format(text=text),
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        logger.warning("Ollama 번역 실패 (%s): %s", text[:40], exc)
        return ""


def _translate_items(model_class, patch_note):
    """단일 모델 클래스의 미번역 항목들을 Ollama로 번역해 저장"""
    items = model_class.objects.filter(
        patch_note=patch_note,
        content_en__isnull=True,
    )
    for item in items:
        translated = _call_ollama(item.content)
        if translated:
            item.content_en = translated
            item.save(update_fields=["content_en", "updated_at"])


def _run_translation(patch_note_id: int):
    """백그라운드 스레드 진입점 — Django ORM을 안전하게 사용"""
    import django
    from .models import PatchNote, Feature, Improvement, BugFix, Remark

    try:
        patch_note = PatchNote.objects.get(id=patch_note_id)
        for model_class in (Feature, Improvement, BugFix, Remark):
            _translate_items(model_class, patch_note)
        logger.info("패치노트 %s 영문 번역 완료", patch_note_id)
    except PatchNote.DoesNotExist:
        logger.error("번역 대상 패치노트를 찾을 수 없습니다: id=%s", patch_note_id)
    except Exception as exc:
        logger.error("패치노트 %s 번역 중 오류: %s", patch_note_id, exc)


def start_translation(patch_note_id: int):
    """패치노트 등록 후 호출 — 데몬 스레드로 번역 시작"""
    thread = threading.Thread(
        target=_run_translation,
        args=(patch_note_id,),
        daemon=True,
        name=f"translate-patchnote-{patch_note_id}",
    )
    thread.start()

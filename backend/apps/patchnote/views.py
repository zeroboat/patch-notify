import logging
import re

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import TemplateView

from web_project import TemplateLayout
from apps.base.mixins import role_required
from apps.product.models import Product
from .models import PatchNote, Feature, Improvement, BugFix, Remark
from .translation import start_translation

logger = logging.getLogger(__name__)


def _push_to_notion_safe(patch_note, is_new=True):
    """Notion push를 시도하되, 실패해도 DB 저장에는 영향 없게 처리"""
    if not settings.NOTION_ENABLED:
        return
    try:
        from apps.notion.services import push_patch_note_to_notion
        push_patch_note_to_notion(patch_note, is_new=is_new)
    except Exception as e:
        logger.warning(f'Notion push 실패 (v{patch_note.version}): {e}')


class PatchNoteDetailView(LoginRequiredMixin, TemplateView):
    template_name = "patchnote/patch_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)

        product_id = self.kwargs.get('product_id')
        product = get_object_or_404(Product, id=product_id)

        patch_notes = PatchNote.objects.filter(product=product).prefetch_related(
            'features', 'improvements', 'bugfixes', 'remarks'
        ).order_by('-release_date', '-version')

        context.update({
            'selected_product': product,
            'patch_notes': patch_notes,
        })
        return context


# ──────────────────────────────────────────────
# 헬퍼: 섹션 HTML 저장 / 조회
# ──────────────────────────────────────────────

def _save_section(patch_note, html, model_class):
    """CKEditor HTML을 섹션당 1개 레코드로 저장 (실제 텍스트 없으면 건너뜀)"""
    html = (html or '').strip()
    if not html:
        return
    # 내용이 없는 <p> 태그 먼저 제거 (<p>&nbsp;</p>, <p><br></p> 등)
    html = re.sub(r'<p(?=\s|>)[^>]*>(\s|&nbsp;|<br\s*/?>)*</p>', '', html)
    # <p> 태그 제거 (내용은 유지, <pre> 등은 건드리지 않음)
    html = re.sub(r'<p(?=\s|>)[^>]*>', '', html)
    html = re.sub(r'</p>', '', html)
    html = html.strip()
    # 태그 제거 후 텍스트가 없으면 저장 안 함 (&nbsp; 엔티티 문자열도 함께 처리)
    text_only = re.sub(r'<[^>]+>', '', html).replace('\xa0', '').replace('&nbsp;', '').strip()
    if not text_only:
        return
    model_class.objects.create(patch_note=patch_note, content=html, order=0)


def _get_section_html(manager):
    """섹션의 저장된 HTML 반환 (수정 모달용)"""
    obj = manager.filter(parent__isnull=True).order_by('order', 'id').first()
    return obj.content if obj else ''


# ──────────────────────────────────────────────
# 패치노트 등록 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_append(request):
    print(request.POST)  # 디버깅용 로그
    try:
        product_id  = request.POST.get('product_id', '').strip()
        version     = request.POST.get('version', '').strip()
        patch_date  = request.POST.get('patch_date', '').strip()

        new_features_html  = request.POST.get('new_features', '')
        improvements_html  = request.POST.get('improvements', '')
        bug_fixes_html     = request.POST.get('bug_fixes', '')
        special_notes_html = request.POST.get('special_notes', '')

        if not product_id:
            return JsonResponse({'error': '제품 정보가 누락되었습니다.'}, status=400)
        if not version:
            return JsonResponse({'error': '버전을 입력해주세요.'}, status=400)
        if not patch_date:
            return JsonResponse({'error': '배포 날짜를 입력해주세요.'}, status=400)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=400)

        patch_note, created = PatchNote.objects.get_or_create(
            product=product,
            version=version,
            defaults={'release_date': patch_date},
        )
        if not created:
            return JsonResponse(
                {'error': f'버전 {version}은 이미 등록되어 있습니다.'},
                status=400,
            )

        _save_section(patch_note, new_features_html,  Feature)
        _save_section(patch_note, improvements_html,  Improvement)
        _save_section(patch_note, bug_fixes_html,     BugFix)
        _save_section(patch_note, special_notes_html, Remark)

        patch_note.translation_status = PatchNote.TRANSLATION_PENDING
        patch_note.save(update_fields=["translation_status", "updated_at"])
        start_translation(patch_note.id)
        _push_to_notion_safe(patch_note, is_new=True)

        return JsonResponse({'message': '패치노트가 등록되었습니다.', 'patch_note_id': patch_note.id})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 패치노트 데이터 조회 API (수정 모달용)
# ──────────────────────────────────────────────

@require_GET
@role_required('dev')
def get_patch_note_data(request, patch_note_id):
    try:
        note = PatchNote.objects.prefetch_related(
            'features', 'improvements', 'bugfixes', 'remarks',
        ).get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    return JsonResponse({
        'id': note.id,
        'version': note.version,
        'release_date': str(note.release_date),
        'features_html':     _get_section_html(note.features),
        'improvements_html': _get_section_html(note.improvements),
        'bugfixes_html':     _get_section_html(note.bugfixes),
        'remarks_html':      _get_section_html(note.remarks),
    })


# ──────────────────────────────────────────────
# 패치노트 수정 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_update(request):
    try:
        patch_note_id      = request.POST.get('patch_note_id', '').strip()
        version            = request.POST.get('version', '').strip()
        patch_date         = request.POST.get('patch_date', '').strip()

        new_features_html  = request.POST.get('new_features', '')
        improvements_html  = request.POST.get('improvements', '')
        bug_fixes_html     = request.POST.get('bug_fixes', '')
        special_notes_html = request.POST.get('special_notes', '')

        if not patch_note_id:
            return JsonResponse({'error': '패치노트 ID가 누락되었습니다.'}, status=400)
        if not version:
            return JsonResponse({'error': '버전을 입력해주세요.'}, status=400)
        if not patch_date:
            return JsonResponse({'error': '배포 날짜를 입력해주세요.'}, status=400)

        try:
            note = PatchNote.objects.get(id=patch_note_id)
        except PatchNote.DoesNotExist:
            return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

        if PatchNote.objects.filter(product=note.product, version=version).exclude(id=note.id).exists():
            return JsonResponse({'error': f'버전 {version}은 이미 등록되어 있습니다.'}, status=400)

        note.version = version
        note.release_date = patch_date
        note.save()

        note.features.all().delete()
        note.improvements.all().delete()
        note.bugfixes.all().delete()
        note.remarks.all().delete()

        _save_section(note, new_features_html,  Feature)
        _save_section(note, improvements_html,  Improvement)
        _save_section(note, bug_fixes_html,     BugFix)
        _save_section(note, special_notes_html, Remark)

        note.translation_status = PatchNote.TRANSLATION_PENDING
        note.save(update_fields=["translation_status", "updated_at"])
        start_translation(note.id)
        _push_to_notion_safe(note, is_new=False)

        return JsonResponse({'message': '패치노트가 수정되었습니다.', 'patch_note_id': note.id})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 패치노트 삭제 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_delete(request):
    try:
        patch_note_id = request.POST.get('patch_note_id', '').strip()
        if not patch_note_id:
            return JsonResponse({'error': '패치노트 ID가 누락되었습니다.'}, status=400)

        try:
            note = PatchNote.objects.get(id=patch_note_id)
        except PatchNote.DoesNotExist:
            return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

        version = note.version
        note.delete()
        return JsonResponse({'message': f'버전 {version} 패치노트가 삭제되었습니다.'})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 번역 상태 확인 API
# ──────────────────────────────────────────────

@require_GET
@role_required('dev')
def translation_status(request, patch_note_id):
    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    return JsonResponse({
        'patch_note_id': note.id,
        'status': note.translation_status,
    })

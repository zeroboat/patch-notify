import html as html_module
from html.parser import HTMLParser

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from web_project import TemplateLayout
from apps.product.models import Product
from .models import PatchNote, Feature, Improvement, BugFix, Remark


class PatchNoteDetailView(TemplateView):
    template_name = "patchnote/patch_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)

        product_id = self.kwargs.get('product_id')
        product = get_object_or_404(Product, id=product_id)

        patch_notes = PatchNote.objects.filter(product=product).prefetch_related(
            'features__children',
            'improvements__children',
            'bugfixes__children',
            'remarks__children'
        ).order_by('-release_date', '-version')

        context.update({
            'selected_product': product,
            'patch_notes': patch_notes,
        })
        return context


# ──────────────────────────────────────────────
# CKEditor HTML → (text, depth) 파서
# ──────────────────────────────────────────────

class _ListItemParser(HTMLParser):
    """CKEditor <ul><li> HTML을 (text, depth) 목록으로 파싱"""

    def __init__(self):
        super().__init__()
        self.items = []
        self._stack = []   # {'text_parts': [], 'depth': int, 'capture': bool}
        self._depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag in ('ul', 'ol'):
            self._depth += 1
            # 중첩 리스트 진입 시 부모 <li> 텍스트 캡처 중단
            if self._stack:
                self._stack[-1]['capture'] = False
        elif tag == 'li':
            self._stack.append({'text_parts': [], 'depth': self._depth, 'capture': True})

    def handle_endtag(self, tag):
        if tag in ('ul', 'ol'):
            self._depth -= 1
        elif tag == 'li':
            if self._stack:
                item = self._stack.pop()
                text = html_module.unescape(''.join(item['text_parts']))
                text = text.replace('\xa0', ' ').strip()
                if text:
                    self.items.append({'text': text, 'depth': item['depth']})

    def handle_data(self, data):
        if self._stack and self._stack[-1]['capture']:
            self._stack[-1]['text_parts'].append(data)


def _parse_list_html(html_content):
    """CKEditor HTML 문자열 → [{'text': str, 'depth': int}] 반환"""
    if not html_content or not html_content.strip():
        return []
    parser = _ListItemParser()
    parser.feed(html_content)
    return parser.items


def _create_items(patch_note, items, model_class):
    """파싱된 항목을 계층 구조로 DB에 저장 (depth 1 = 부모, depth 2+ = 자식)"""
    last_parent = None
    for order, item in enumerate(items):
        if item['depth'] == 1:
            obj = model_class.objects.create(
                patch_note=patch_note,
                content=item['text'],
                order=order,
                parent=None,
            )
            last_parent = obj
        else:
            model_class.objects.create(
                patch_note=patch_note,
                content=item['text'],
                order=order,
                parent=last_parent,
            )


# ──────────────────────────────────────────────
# 패치노트 등록 API
# ──────────────────────────────────────────────

@require_POST
def patch_note_append(request):
    try:
        product_id  = request.POST.get('product_id', '').strip()
        version     = request.POST.get('version', '').strip()
        patch_date  = request.POST.get('patch_date', '').strip()

        new_features_html  = request.POST.get('new_features', '')
        improvements_html  = request.POST.get('improvements', '')
        bug_fixes_html     = request.POST.get('bug_fixes', '')
        special_notes_html = request.POST.get('special_notes', '')

        # ── 필수 값 검증 ──
        if not product_id:
            return JsonResponse({'error': '제품 정보가 누락되었습니다.'}, status=400)
        if not version:
            return JsonResponse({'error': '버전을 입력해주세요.'}, status=400)
        if not patch_date:
            return JsonResponse({'error': '배포 날짜를 입력해주세요.'}, status=400)

        # ── 제품 조회 ──
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=400)

        # ── PatchNote 생성 (중복 버전 차단) ──
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

        # ── 각 섹션 파싱 & 저장 ──
        _create_items(patch_note, _parse_list_html(new_features_html),  Feature)
        _create_items(patch_note, _parse_list_html(improvements_html),  Improvement)
        _create_items(patch_note, _parse_list_html(bug_fixes_html),     BugFix)
        _create_items(patch_note, _parse_list_html(special_notes_html), Remark)

        return JsonResponse({'message': '패치노트가 등록되었습니다.', 'patch_note_id': patch_note.id})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)

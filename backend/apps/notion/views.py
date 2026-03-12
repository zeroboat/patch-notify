import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.product.models import Product
from .models import NotionPageMapping
from .services import sync_product

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 매핑 관리 페이지
# ──────────────────────────────────────────────

class NotionManagementView(RoleRequiredMixin, TemplateView):
    """Admin 전용: Notion 페이지 매핑 관리"""
    allowed_roles = []
    template_name = "notion/notion_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        mappings = NotionPageMapping.objects.select_related(
            'product', 'product__solution'
        ).order_by('product__solution__name', 'product__platform')

        mapped_product_ids = set(mappings.values_list('product_id', flat=True))
        unmapped_products = Product.objects.select_related('solution').exclude(
            id__in=mapped_product_ids
        ).order_by('solution__name', 'platform')

        context.update({
            'mappings': mappings,
            'unmapped_products': unmapped_products,
            'unmapped_count': unmapped_products.count(),
        })
        return context


# ──────────────────────────────────────────────
# 매핑 CRUD
# ──────────────────────────────────────────────

@require_POST
@role_required()
def create_mapping(request):
    product_id = request.POST.get('product_id', '').strip()
    page_id_ko = request.POST.get('page_id_ko', '').strip()
    page_id_en = request.POST.get('page_id_en', '').strip()

    if not product_id or not page_id_ko:
        return JsonResponse({'error': '제품과 한국어 페이지 ID는 필수입니다.'}, status=400)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=404)

    if NotionPageMapping.objects.filter(product=product).exists():
        return JsonResponse({'error': '이미 매핑이 등록된 제품입니다.'}, status=400)

    NotionPageMapping.objects.create(
        product=product,
        page_id_ko=page_id_ko,
        page_id_en=page_id_en,
    )
    return JsonResponse({'message': f'{product} 매핑이 등록되었습니다.'})


@require_POST
@role_required()
def update_mapping(request):
    mapping_id = request.POST.get('mapping_id', '').strip()
    page_id_ko = request.POST.get('page_id_ko', '').strip()
    page_id_en = request.POST.get('page_id_en', '').strip()

    if not mapping_id or not page_id_ko:
        return JsonResponse({'error': '매핑 ID와 한국어 페이지 ID는 필수입니다.'}, status=400)

    try:
        mapping = NotionPageMapping.objects.get(id=mapping_id)
    except NotionPageMapping.DoesNotExist:
        return JsonResponse({'error': '매핑을 찾을 수 없습니다.'}, status=404)

    mapping.page_id_ko = page_id_ko
    mapping.page_id_en = page_id_en
    mapping.save()
    return JsonResponse({'message': '매핑이 수정되었습니다.'})


@require_POST
@role_required()
def delete_mapping(request):
    mapping_id = request.POST.get('mapping_id', '').strip()

    try:
        mapping = NotionPageMapping.objects.select_related('product').get(id=mapping_id)
    except NotionPageMapping.DoesNotExist:
        return JsonResponse({'error': '매핑을 찾을 수 없습니다.'}, status=404)

    name = str(mapping.product)
    mapping.delete()
    return JsonResponse({'message': f'{name} 매핑이 삭제되었습니다.'})


# ──────────────────────────────────────────────
# Notion 동기화 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def notion_sync(request):
    """특정 Product의 Notion 데이터를 동기화"""
    if not settings.NOTION_ENABLED:
        return JsonResponse({'error': 'Notion 연동이 비활성화되어 있습니다.'}, status=400)

    if not settings.NOTION_TOKEN:
        return JsonResponse({'error': 'NOTION_TOKEN이 설정되지 않았습니다.'}, status=400)

    product_id = request.POST.get('product_id', '').strip()
    version = request.POST.get('version', '').strip() or None

    if not product_id:
        return JsonResponse({'error': '제품 ID가 누락되었습니다.'}, status=400)

    try:
        mapping = NotionPageMapping.objects.select_related('product').get(product_id=product_id)
    except NotionPageMapping.DoesNotExist:
        return JsonResponse({'error': '해당 제품의 Notion 매핑 정보가 없습니다.'}, status=404)

    try:
        stats = sync_product(mapping, version=version)
        msg = f'동기화 완료 — 신규: {stats["created"]}, 갱신: {stats["updated"]}, 건너뜀: {stats["skipped"]}'
        return JsonResponse({'message': msg, **stats})
    except Exception as e:
        logger.exception(f'Notion 동기화 실패 (product_id={product_id})')
        return JsonResponse({'error': f'동기화 실패: {str(e)}'}, status=500)

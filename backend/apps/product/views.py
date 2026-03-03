from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib import messages
from django.db.models import Max, Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from .models import Product, Solution


class ProductManagementView(RoleRequiredMixin, TemplateView):
    """Admin 전용: 제품/솔루션 관리"""
    allowed_roles = []
    template_name = "product/product_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        solutions = Solution.objects.prefetch_related(
            Prefetch(
                'products',
                queryset=Product.objects.annotate(
                    latest_release=Max('patch_notes__release_date')
                ).order_by('platform', 'category')
            )
        ).order_by('id')

        total_products = Product.objects.count()

        context.update({
            'solutions': solutions,
            'total_products': total_products,
        })
        return context


@role_required()
def create_solution(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        icon = request.POST.get('icon', '').strip() or 'bx-layer'
        if name:
            Solution.objects.create(name=name, icon=icon)
            messages.success(request, f'솔루션 "{name}"이 등록되었습니다.')
        else:
            messages.error(request, '솔루션 이름을 입력해주세요.')
    return redirect('product:product_management')


@role_required()
def create_product(request):
    if request.method == 'POST':
        solution_id = request.POST.get('solution_id')
        platform = request.POST.get('platform')
        category = request.POST.get('category')
        description = request.POST.get('description', '').strip()

        try:
            solution = Solution.objects.get(id=solution_id)
            Product.objects.create(
                solution=solution,
                platform=platform,
                category=category,
                description=description or None,
            )
            messages.success(request, '제품이 등록되었습니다.')
        except Solution.DoesNotExist:
            messages.error(request, '선택한 솔루션을 찾을 수 없습니다.')
        except Exception as e:
            messages.error(request, f'등록 중 오류가 발생했습니다: {e}')

    return redirect('product:product_management')


@require_POST
@role_required()
def update_product(request):
    product_id = request.POST.get('product_id', '').strip()
    platform    = request.POST.get('platform', '').strip()
    category    = request.POST.get('category', '').strip()
    description = request.POST.get('description', '').strip()

    if not product_id:
        return JsonResponse({'error': '제품 ID가 누락되었습니다.'}, status=400)
    if not platform or not category:
        return JsonResponse({'error': '플랫폼과 카테고리는 필수입니다.'}, status=400)

    try:
        product = Product.objects.get(id=product_id)
        product.platform    = platform
        product.category    = category
        product.description = description or None
        product.save()
        return JsonResponse({'message': '제품 정보가 수정되었습니다.'})
    except Product.DoesNotExist:
        return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'수정 중 오류가 발생했습니다: {e}'}, status=500)


@require_POST
@role_required()
def delete_product(request):
    product_id = request.POST.get('product_id', '').strip()
    try:
        product = Product.objects.get(id=product_id)
        name = str(product)
        product.delete()
        return JsonResponse({'message': f'제품 "{name}"이 삭제되었습니다.'})
    except Product.DoesNotExist:
        return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'삭제 중 오류가 발생했습니다: {e}'}, status=500)


@require_POST
@role_required()
def delete_solution(request):
    solution_id = request.POST.get('solution_id', '').strip()
    try:
        solution = Solution.objects.get(id=solution_id)
        if solution.products.exists():
            return JsonResponse(
                {'error': '솔루션에 제품이 등록되어 있어 삭제할 수 없습니다. 제품을 먼저 삭제해주세요.'},
                status=400
            )
        name = solution.name
        solution.delete()
        return JsonResponse({'message': f'솔루션 "{name}"이 삭제되었습니다.'})
    except Solution.DoesNotExist:
        return JsonResponse({'error': '솔루션을 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'삭제 중 오류가 발생했습니다: {e}'}, status=500)

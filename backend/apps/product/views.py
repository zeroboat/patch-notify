from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib import messages
from django.db.models import Max, Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from .models import Product, Solution, Utility


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
                ).order_by('order', 'platform', 'category')
            )
        ).order_by('order', 'id')

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
        order = request.POST.get('order', '0').strip()
        if name:
            Solution.objects.create(name=name, icon=icon, order=int(order or 0))
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
        order = request.POST.get('order', '0').strip()

        try:
            solution = Solution.objects.get(id=solution_id)
            Product.objects.create(
                solution=solution,
                platform=platform,
                category=category,
                description=description or None,
                order=int(order or 0),
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

    order = request.POST.get('order', '').strip()

    try:
        product = Product.objects.get(id=product_id)
        product.platform    = platform
        product.category    = category
        product.description = description or None
        if order:
            product.order = int(order)
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
def update_solution(request):
    solution_id = request.POST.get('solution_id', '').strip()
    name = request.POST.get('name', '').strip()
    icon = request.POST.get('icon', '').strip()
    order = request.POST.get('order', '').strip()

    if not solution_id:
        return JsonResponse({'error': '솔루션 ID가 누락되었습니다.'}, status=400)

    try:
        solution = Solution.objects.get(id=solution_id)
        if name:
            solution.name = name
        if icon:
            solution.icon = icon
        if order:
            solution.order = int(order)
        solution.save()
        return JsonResponse({'message': f'솔루션 "{solution.name}" 정보가 수정되었습니다.'})
    except Solution.DoesNotExist:
        return JsonResponse({'error': '솔루션을 찾을 수 없습니다.'}, status=404)
    except (ValueError, TypeError):
        return JsonResponse({'error': '순서 값이 올바르지 않습니다.'}, status=400)


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


# ---------------------------------------------------------------------------
# Utility Management Views
# ---------------------------------------------------------------------------

class UtilityManagementView(RoleRequiredMixin, TemplateView):
    """Admin 전용: 유틸리티/툴 솔루션 관리"""
    allowed_roles = []
    template_name = "product/utility_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        tool_solutions = Solution.objects.filter(solution_type=Solution.TYPE_TOOL).prefetch_related(
            Prefetch(
                'utilities',
                queryset=Utility.objects.annotate(
                    latest_release=Max('patch_notes__release_date')
                ).order_by('order', 'name')
            )
        ).order_by('order', 'id')

        total_utilities = Utility.objects.filter(
            solution__solution_type=Solution.TYPE_TOOL
        ).count()

        context.update({
            'tool_solutions': tool_solutions,
            'total_utilities': total_utilities,
        })
        return context


@role_required()
def create_utility_solution(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        icon = request.POST.get('icon', '').strip() or 'bx-wrench'
        order = request.POST.get('order', '0').strip()
        if name:
            Solution.objects.create(
                name=name,
                icon=icon,
                order=int(order or 0),
                solution_type=Solution.TYPE_TOOL,
            )
            messages.success(request, f'툴 솔루션 "{name}"이 등록되었습니다.')
        else:
            messages.error(request, '솔루션 이름을 입력해주세요.')
    return redirect('product:utility_management')


@role_required()
def create_utility(request):
    if request.method == 'POST':
        solution_id = request.POST.get('solution_id')
        name = request.POST.get('name', '').strip()
        order = request.POST.get('order', '0').strip()

        try:
            solution = Solution.objects.get(id=solution_id, solution_type=Solution.TYPE_TOOL)
            Utility.objects.create(
                solution=solution,
                name=name,
                order=int(order or 0),
            )
            messages.success(request, f'유틸리티 "{name}"이 등록되었습니다.')
        except Solution.DoesNotExist:
            messages.error(request, '선택한 툴 솔루션을 찾을 수 없습니다.')
        except Exception as e:
            messages.error(request, f'등록 중 오류가 발생했습니다: {e}')

    return redirect('product:utility_management')


@require_POST
@role_required()
def update_utility(request):
    utility_id = request.POST.get('utility_id', '').strip()
    name = request.POST.get('name', '').strip()
    order = request.POST.get('order', '').strip()

    if not utility_id:
        return JsonResponse({'error': '유틸리티 ID가 누락되었습니다.'}, status=400)
    if not name:
        return JsonResponse({'error': '유틸리티 이름은 필수입니다.'}, status=400)

    try:
        utility = Utility.objects.get(id=utility_id)
        utility.name = name
        if order:
            utility.order = int(order)
        utility.save()
        return JsonResponse({'message': f'유틸리티 "{utility.name}" 정보가 수정되었습니다.'})
    except Utility.DoesNotExist:
        return JsonResponse({'error': '유틸리티를 찾을 수 없습니다.'}, status=404)
    except (ValueError, TypeError):
        return JsonResponse({'error': '순서 값이 올바르지 않습니다.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'수정 중 오류가 발생했습니다: {e}'}, status=500)


@require_POST
@role_required()
def delete_utility(request):
    utility_id = request.POST.get('utility_id', '').strip()
    try:
        utility = Utility.objects.get(id=utility_id)
        if utility.patch_notes.exists():
            return JsonResponse(
                {'error': '유틸리티에 패치노트가 등록되어 있어 삭제할 수 없습니다. 패치노트를 먼저 삭제해주세요.'},
                status=400
            )
        name = str(utility)
        utility.delete()
        return JsonResponse({'message': f'유틸리티 "{name}"이 삭제되었습니다.'})
    except Utility.DoesNotExist:
        return JsonResponse({'error': '유틸리티를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'삭제 중 오류가 발생했습니다: {e}'}, status=500)


@require_POST
@role_required()
def update_utility_solution(request):
    solution_id = request.POST.get('solution_id', '').strip()
    name = request.POST.get('name', '').strip()
    icon = request.POST.get('icon', '').strip()
    order = request.POST.get('order', '').strip()

    if not solution_id:
        return JsonResponse({'error': '솔루션 ID가 누락되었습니다.'}, status=400)

    try:
        solution = Solution.objects.get(id=solution_id, solution_type=Solution.TYPE_TOOL)
        if name:
            solution.name = name
        if icon:
            solution.icon = icon
        if order:
            solution.order = int(order)
        solution.save()
        return JsonResponse({'message': f'솔루션 "{solution.name}" 정보가 수정되었습니다.'})
    except Solution.DoesNotExist:
        return JsonResponse({'error': '솔루션을 찾을 수 없습니다.'}, status=404)
    except (ValueError, TypeError):
        return JsonResponse({'error': '순서 값이 올바르지 않습니다.'}, status=400)


@require_POST
@role_required()
def delete_utility_solution(request):
    solution_id = request.POST.get('solution_id', '').strip()
    try:
        solution = Solution.objects.get(id=solution_id, solution_type=Solution.TYPE_TOOL)
        if solution.utilities.exists():
            return JsonResponse(
                {'error': '솔루션에 유틸리티가 등록되어 있어 삭제할 수 없습니다. 유틸리티를 먼저 삭제해주세요.'},
                status=400
            )
        name = solution.name
        solution.delete()
        return JsonResponse({'message': f'솔루션 "{name}"이 삭제되었습니다.'})
    except Solution.DoesNotExist:
        return JsonResponse({'error': '솔루션을 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'삭제 중 오류가 발생했습니다: {e}'}, status=500)

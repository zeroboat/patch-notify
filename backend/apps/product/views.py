from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib import messages
from django.db.models import Max, Prefetch
from web_project import TemplateLayout
from .models import Product, Solution


class ProductManagementView(TemplateView):
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
        ).order_by('name')

        total_products = Product.objects.count()

        context.update({
            'solutions': solutions,
            'total_products': total_products,
        })
        return context


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

from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from .models import Customer, CustomerEmail
from apps.product.models import Solution


class CustomerManagementView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 고객사 관리"""
    allowed_roles = ['se']
    template_name = "customer/customer_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        customers = Customer.objects.prefetch_related('emails', 'solutions').order_by('name')
        solutions = Solution.objects.order_by('name')
        context.update({
            'customers': customers,
            'solutions': solutions,
            'total_customers': customers.count(),
        })
        return context


@role_required('se')
def create_customer(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            Customer.objects.create(name=name)
            messages.success(request, f'고객사 "{name}"이 등록되었습니다.')
        else:
            messages.error(request, '고객사명을 입력해주세요.')
    return redirect('customer:customer_management')


@require_POST
@role_required('se')
def add_email(request):
    customer_id = request.POST.get('customer_id')
    email = request.POST.get('email', '').strip()
    name = request.POST.get('name', '').strip()

    try:
        customer = Customer.objects.get(id=customer_id)
        if not email:
            return JsonResponse({'error': '이메일을 입력해주세요.'}, status=400)
        obj, created = CustomerEmail.objects.get_or_create(
            customer=customer,
            email=email,
            defaults={'name': name or None},
        )
        if not created:
            return JsonResponse({'error': '이미 등록된 이메일입니다.'}, status=400)
        return JsonResponse({'message': f'이메일 {email}이 등록되었습니다.', 'email_id': obj.id})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def delete_email(request):
    email_id = request.POST.get('email_id')
    try:
        email_obj = CustomerEmail.objects.get(id=email_id)
        email_addr = email_obj.email
        email_obj.delete()
        return JsonResponse({'message': f'{email_addr}이 삭제되었습니다.'})
    except CustomerEmail.DoesNotExist:
        return JsonResponse({'error': '이메일을 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def delete_customer(request):
    customer_id = request.POST.get('customer_id')
    try:
        customer = Customer.objects.get(id=customer_id)
        name = customer.name
        customer.delete()
        return JsonResponse({'message': f'"{name}"이 삭제되었습니다.'})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)


@require_POST
@role_required('se')
def update_customer(request):
    customer_id = request.POST.get('customer_id')
    name = request.POST.get('name', '').strip()
    solution_ids = request.POST.getlist('solution_ids')

    try:
        customer = Customer.objects.get(id=customer_id)
        if name:
            customer.name = name
            customer.save()
        customer.solutions.set(solution_ids)
        return JsonResponse({'message': f'"{customer.name}" 정보가 저장되었습니다.'})
    except Customer.DoesNotExist:
        return JsonResponse({'error': '고객사를 찾을 수 없습니다.'}, status=404)

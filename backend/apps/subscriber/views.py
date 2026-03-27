from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.customer.models import Customer
from apps.product.models import Product
from .models import Subscription


class SubscriberManagementView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 구독 관리"""
    allowed_roles = ['se']
    template_name = "subscriber/subscriber_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        customers = (
            Customer.objects
            .prefetch_related(
                'solutions',
                'subscriptions__product__solution',
            )
            .order_by('name')
        )

        customer_rows = []
        for c in customers:
            subs = list(c.subscriptions.filter(is_active=True).select_related('product__solution'))
            email_subs = sorted({s.product.solution.name for s in subs if s.channel == Subscription.CHANNEL_EMAIL})
            slack_subs = sorted({s.product.solution.name for s in subs if s.channel == Subscription.CHANNEL_SLACK})
            customer_rows.append({
                'id': c.id,
                'name': c.name,
                'email_subs': email_subs,
                'slack_subs': slack_subs,
                'total': len(email_subs) + len(slack_subs),
            })

        context['customer_rows'] = customer_rows
        context['total_customers'] = len(customer_rows)
        return context


@require_GET
@role_required('se')
def get_customer_subscriptions(request, customer_id):
    """Admin+SE AJAX: 특정 고객사의 구매 솔루션 > 제품별 구독 설정 반환"""
    try:
        customer = Customer.objects.prefetch_related('solutions__products').get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'}, status=404)

    existing = {
        (s.product_id, s.channel): s
        for s in Subscription.objects.filter(customer=customer)
    }

    solutions_data = []
    for sol in customer.solutions.order_by('order', 'id'):
        products_data = []
        for prod in sol.products.all():
            email_sub = existing.get((prod.id, Subscription.CHANNEL_EMAIL))
            slack_sub = existing.get((prod.id, Subscription.CHANNEL_SLACK))
            products_data.append({
                'id': prod.id,
                'platform': prod.get_platform_display(),
                'category': prod.get_category_display(),
                'email': {
                    'active': email_sub.is_active if email_sub else False,
                    'max_items': email_sub.max_items if email_sub else 5,
                },
                'slack': {
                    'active': slack_sub.is_active if slack_sub else False,
                    'max_items': slack_sub.max_items if slack_sub else 5,
                    'slack_channel': slack_sub.slack_channel or '' if slack_sub else '',
                },
            })
        solutions_data.append({
            'id': sol.id,
            'name': sol.name,
            'products': products_data,
        })

    return JsonResponse({
        'ok': True,
        'customer_name': customer.name,
        'solutions': solutions_data,
    })


@require_POST
@role_required('se')
def save_customer_subscription(request):
    """Admin+SE AJAX: 고객사+제품 단위 Gmail/Slack 구독 저장"""
    customer_id = request.POST.get('customer_id')
    product_id = request.POST.get('product_id')

    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'})

    try:
        product = Product.objects.select_related('solution').get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '제품을 찾을 수 없습니다.'})

    if not customer.solutions.filter(pk=product.solution_id).exists():
        return JsonResponse({'ok': False, 'error': '해당 솔루션의 구독 권한이 없습니다.'})

    # Gmail
    email_active = request.POST.get('email_active') == 'true'
    email_max_items = int(request.POST.get('email_max_items', 5))

    if email_active:
        Subscription.objects.update_or_create(
            customer=customer,
            product=product,
            channel=Subscription.CHANNEL_EMAIL,
            defaults={
                'is_active': True,
                'max_items': max(1, min(10, email_max_items)),
            },
        )
    else:
        Subscription.objects.filter(
            customer=customer, product=product, channel=Subscription.CHANNEL_EMAIL
        ).delete()

    # Slack
    slack_active = request.POST.get('slack_active') == 'true'
    slack_max_items = int(request.POST.get('slack_max_items', 5))
    slack_channel = request.POST.get('slack_channel', '').strip()

    if slack_active:
        Subscription.objects.update_or_create(
            customer=customer,
            product=product,
            channel=Subscription.CHANNEL_SLACK,
            defaults={
                'is_active': True,
                'max_items': max(1, min(10, slack_max_items)),
                'slack_channel': slack_channel or None,
            },
        )
    else:
        Subscription.objects.filter(
            customer=customer, product=product, channel=Subscription.CHANNEL_SLACK
        ).delete()

    label = f"{product.solution.name} {product.get_platform_display()} {product.get_category_display()}"
    return JsonResponse({'ok': True, 'message': f'{label} 구독 설정이 저장되었습니다.'})

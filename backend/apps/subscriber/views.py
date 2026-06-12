from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.customer.models import Customer
from apps.product.models import Product, Solution
from .models import Subscription, CustomerSubscriptionToken, SubscriptionEmail


class SubscriberManagementView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 구독 관리"""
    allowed_roles = ['se']
    template_name = "subscriber/subscriber_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        customers = list(
            Customer.objects
            .prefetch_related('solutions', 'subscriptions__product__solution')
            .order_by('name')
        )
        customer_ids = [c.id for c in customers]
        tokens_map = {
            t.customer_id: t
            for t in CustomerSubscriptionToken.objects.filter(customer_id__in=customer_ids)
        }

        now = timezone.now()
        customer_rows = []
        for c in customers:
            subs = list(c.subscriptions.filter(is_active=True).select_related('product__solution'))
            email_subs = sorted({s.product.solution.name for s in subs if s.channel == Subscription.CHANNEL_EMAIL})
            slack_subs = sorted({s.product.solution.name for s in subs if s.channel == Subscription.CHANNEL_SLACK})

            tok = tokens_map.get(c.id)
            if tok:
                days_left = (tok.expires_at - now).days
                token_info = {
                    'exists': True,
                    'token': str(tok.token),
                    'expires_at': tok.expires_at.strftime('%Y-%m-%d %H:%M'),
                    'is_expired': tok.is_expired,
                    'days_left': max(0, days_left),
                }
            else:
                token_info = {'exists': False}

            customer_rows.append({
                'id': c.id,
                'name': c.name,
                'email_subs': email_subs,
                'slack_subs': slack_subs,
                'solutions_count': c.solutions.count(),
                'total': len(email_subs) + len(slack_subs),
                'token': token_info,
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
    from apps.logs.models import ActionLog
    ActionLog.record(request, ActionLog.SUBSCRIPTION_CHANGE,
                     f'{customer.name} / {label}',
                     {'email_active': email_active, 'slack_active': slack_active})
    return JsonResponse({'ok': True, 'message': f'{label} 구독 설정이 저장되었습니다.'})


# ── 구독 링크 발행 / 취소 (관리자) ──────────────────────────────────────────────

@require_POST
@role_required('se')
def issue_token(request, customer_id):
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'}, status=404)

    expires_at_str = request.POST.get('expires_at', '').strip()
    try:
        expires_at = parse_datetime(expires_at_str)
        if not expires_at:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': '만료일시를 올바르게 입력해주세요.'})

    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at)

    import uuid
    token_obj, _ = CustomerSubscriptionToken.objects.update_or_create(
        customer=customer,
        defaults={
            'token': uuid.uuid4(),
            'expires_at': expires_at,
            'created_by': request.user,
        },
    )

    url = request.build_absolute_uri(f'/subscriber/subscribe/{token_obj.token}/')
    return JsonResponse({
        'ok': True,
        'token': str(token_obj.token),
        'expires_at': token_obj.expires_at.strftime('%Y-%m-%d %H:%M'),
        'url': url,
    })


@require_POST
@role_required('se')
def revoke_token(request, customer_id):
    CustomerSubscriptionToken.objects.filter(customer_id=customer_id).delete()
    return JsonResponse({'ok': True})


# ── 고객사 공개 구독 페이지 ─────────────────────────────────────────────────────

def _get_valid_token(token_str):
    """토큰 문자열로 유효한 CustomerSubscriptionToken 반환. 없거나 만료 시 None."""
    try:
        obj = CustomerSubscriptionToken.objects.select_related('customer').get(token=token_str)
    except CustomerSubscriptionToken.DoesNotExist:
        return None
    if obj.is_expired:
        return None
    return obj


def subscribe_page(request, token):
    try:
        tok = CustomerSubscriptionToken.objects.select_related('customer').get(token=token)
    except CustomerSubscriptionToken.DoesNotExist:
        return render(request, 'subscriber/subscribe_result.html', {
            'error': '유효하지 않은 링크입니다.',
        })

    if tok.is_expired:
        return render(request, 'subscriber/subscribe_result.html', {
            'error': '만료된 링크입니다. 담당자에게 새 링크를 요청해주세요.',
        })

    customer = tok.customer
    solutions = customer.solutions.prefetch_related('products').order_by('order', 'id')

    active_sol_ids = set(
        Subscription.objects.filter(
            customer=customer,
            channel=Subscription.CHANNEL_EMAIL,
            is_active=True,
        ).values_list('product__solution_id', flat=True).distinct()
    )

    solutions_data = [
        {'id': sol.id, 'name': sol.name, 'active': sol.id in active_sol_ids}
        for sol in solutions
    ]
    emails = list(customer.subscription_emails.order_by('id'))
    days_left = (tok.expires_at - timezone.now()).days

    return render(request, 'subscriber/subscribe.html', {
        'token': str(token),
        'customer': customer,
        'solutions': solutions_data,
        'emails': emails,
        'expires_at': tok.expires_at,
        'is_near_expiry': days_left <= 7,
    })


@require_POST
def subscribe_toggle_solution(request, token):
    tok = _get_valid_token(token)
    if not tok:
        return JsonResponse({'ok': False, 'error': '유효하지 않거나 만료된 링크입니다.'}, status=403)

    customer = tok.customer
    solution_id = request.POST.get('solution_id')
    enabled = request.POST.get('enabled') == 'true'

    try:
        solution = Solution.objects.prefetch_related('products').get(pk=solution_id)
    except Solution.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '솔루션을 찾을 수 없습니다.'})

    if not customer.solutions.filter(pk=solution_id).exists():
        return JsonResponse({'ok': False, 'error': '권한이 없습니다.'}, status=403)

    if enabled:
        for product in solution.products.all():
            obj, created = Subscription.objects.get_or_create(
                customer=customer, product=product, channel=Subscription.CHANNEL_EMAIL,
                defaults={'is_active': True, 'max_items': 5},
            )
            if not created and not obj.is_active:
                obj.is_active = True
                obj.save(update_fields=['is_active'])
    else:
        Subscription.objects.filter(
            customer=customer, product__solution=solution, channel=Subscription.CHANNEL_EMAIL,
        ).update(is_active=False)

    return JsonResponse({'ok': True})


@require_POST
def subscribe_add_email(request, token):
    tok = _get_valid_token(token)
    if not tok:
        return JsonResponse({'ok': False, 'error': '유효하지 않거나 만료된 링크입니다.'}, status=403)

    email = request.POST.get('email', '').strip().lower()
    name = request.POST.get('name', '').strip()

    if not email:
        return JsonResponse({'ok': False, 'error': '이메일을 입력해주세요.'})

    obj, created = SubscriptionEmail.objects.get_or_create(
        customer=tok.customer, email=email,
        defaults={'name': name or ''},
    )
    if not created:
        return JsonResponse({'ok': False, 'error': '이미 등록된 이메일입니다.'})

    return JsonResponse({'ok': True, 'id': obj.id, 'email': obj.email, 'name': obj.name or ''})


@require_POST
def subscribe_remove_email(request, token):
    tok = _get_valid_token(token)
    if not tok:
        return JsonResponse({'ok': False, 'error': '유효하지 않거나 만료된 링크입니다.'}, status=403)

    email_id = request.POST.get('email_id')
    deleted, _ = SubscriptionEmail.objects.filter(pk=email_id, customer=tok.customer).delete()
    if not deleted:
        return JsonResponse({'ok': False, 'error': '이메일을 찾을 수 없습니다.'})
    return JsonResponse({'ok': True})

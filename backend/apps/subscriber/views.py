from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.customer.models import Customer
from apps.product.models import Product, Solution, Utility
from .models import Subscription, CustomerSubscriptionToken, SubscriptionEmail, UtilitySubscription


class SubscriberManagementView(RoleRequiredMixin, TemplateView):
    """Admin + SE: 구독 관리"""
    allowed_roles = ['se']
    template_name = "subscriber/subscriber_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        customers = list(
            Customer.objects
            .prefetch_related(
                'solutions',
                'subscriptions__product__solution',
                'utility_subscriptions__utility',
            )
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
            utility_subs = sorted({
                us.utility.name
                for us in c.utility_subscriptions.all()
                if us.is_active
            })
            utility_slack_subs = sorted({
                us.utility.name
                for us in c.utility_subscriptions.all()
                if us.is_active and us.slack_channel
            })

            tok = tokens_map.get(c.id)
            if tok:
                days_left = (tok.expires_at - now).days
                token_info = {
                    'exists': True,
                    'token': str(tok.token),
                    'url': tok.url or '',
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
                'utility_subs': utility_subs,
                'utility_slack_subs': utility_slack_subs,
                'email_total': len(email_subs) + len(utility_subs),
                'slack_total': len(slack_subs) + len(utility_slack_subs),
                'solutions_count': c.solutions.count(),
                'total': len(email_subs) + len(slack_subs) + len(utility_subs) + len(utility_slack_subs),
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
                },
                'slack': {
                    'active': slack_sub.is_active if slack_sub else False,
                    'slack_channel': slack_sub.slack_channel or '' if slack_sub else '',
                },
            })
        solutions_data.append({
            'id': sol.id,
            'name': sol.name,
            'products': products_data,
        })

    sub_emails = list(
        SubscriptionEmail.objects
        .filter(customer=customer)
        .order_by('id')
        .values('id', 'email', 'name', 'is_active')
    )

    util_subs = UtilitySubscription.objects.filter(customer=customer).select_related('utility')
    utility_email_subs = sorted({us.utility.name for us in util_subs if us.is_active})
    utility_slack_subs = sorted({us.utility.name for us in util_subs if us.is_active and us.slack_channel})

    return JsonResponse({
        'ok': True,
        'customer_name': customer.name,
        'solutions': solutions_data,
        'subscription_emails': sub_emails,
        'utility_email_subs': utility_email_subs,
        'utility_slack_subs': utility_slack_subs,
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

    if email_active:
        Subscription.objects.update_or_create(
            customer=customer,
            product=product,
            channel=Subscription.CHANNEL_EMAIL,
            defaults={'is_active': True},
        )
    else:
        Subscription.objects.filter(
            customer=customer, product=product, channel=Subscription.CHANNEL_EMAIL
        ).delete()

    # Slack
    slack_active = request.POST.get('slack_active') == 'true'
    slack_channel = request.POST.get('slack_channel', '').strip()

    if slack_active:
        Subscription.objects.update_or_create(
            customer=customer,
            product=product,
            channel=Subscription.CHANNEL_SLACK,
            defaults={
                'is_active': True,
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


# ── 구독 이메일 관리 (관리자) ────────────────────────────────────────────────────

@require_POST
@role_required('se')
def admin_add_subscription_email(request, customer_id):
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'}, status=404)

    email = request.POST.get('email', '').strip().lower()
    name = request.POST.get('name', '').strip()

    if not email:
        return JsonResponse({'ok': False, 'error': '이메일을 입력해주세요.'})

    obj, created = SubscriptionEmail.objects.get_or_create(
        customer=customer, email=email,
        defaults={'name': name or ''},
    )
    if not created:
        return JsonResponse({'ok': False, 'error': '이미 등록된 이메일입니다.'})

    return JsonResponse({'ok': True, 'id': obj.id, 'email': obj.email, 'name': obj.name or ''})


@require_POST
@role_required('se')
def admin_remove_subscription_email(request, customer_id):
    email_id = request.POST.get('email_id')
    deleted, _ = SubscriptionEmail.objects.filter(pk=email_id, customer_id=customer_id).delete()
    if not deleted:
        return JsonResponse({'ok': False, 'error': '이메일을 찾을 수 없습니다.'})
    return JsonResponse({'ok': True})


@require_POST
@role_required('se')
def admin_reactivate_subscription_email(request, customer_id):
    email_id = request.POST.get('email_id')
    updated = SubscriptionEmail.objects.filter(pk=email_id, customer_id=customer_id).update(is_active=True)
    if not updated:
        return JsonResponse({'ok': False, 'error': '이메일을 찾을 수 없습니다.'})
    return JsonResponse({'ok': True})


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
    from apps.config.models import SiteConfig
    new_token = uuid.uuid4()
    subscribe_base = SiteConfig.get().subscribe_base_url or ''
    url = (
        f"{subscribe_base.rstrip('/')}/{new_token}/"
        if subscribe_base
        else request.build_absolute_uri(f'/subscriber/subscribe/{new_token}/')
    )
    token_obj, _ = CustomerSubscriptionToken.objects.update_or_create(
        customer=customer,
        defaults={
            'token': new_token,
            'url': url,
            'expires_at': expires_at,
            'created_by': request.user,
        },
    )

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

    # Gmail 구독
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

    # 유틸리티 Gmail 구독
    utilities_qs = list(Utility.objects.order_by('platform', 'order', 'name'))
    all_utility_subs = {
        us.utility_id: us
        for us in UtilitySubscription.objects.filter(customer=customer)
    }
    utilities_data = [
        {
            'id': u.id,
            'name': u.name,
            'platform': u.get_platform_display_ko(),
            'active': all_utility_subs.get(u.id) is not None and all_utility_subs[u.id].is_active,
        }
        for u in utilities_qs
    ]

    # Slack 구독 (승인된 워크스페이스가 있는 경우)
    has_slack = customer.slack_workspaces.filter(status='approved').exists()

    slack_utilities_data = []
    if has_slack:
        for u in utilities_qs:
            us = all_utility_subs.get(u.id)
            slack_utilities_data.append({
                'id': u.id,
                'name': u.name,
                'platform': u.get_platform_display_ko(),
                'channel': (us.slack_channel or '') if us else '',
                'active': (us.is_active if us else False),
            })

    slack_solutions_data = []
    if has_slack:
        slack_subs = {
            (s.product_id,): s
            for s in Subscription.objects.filter(customer=customer, channel=Subscription.CHANNEL_SLACK)
        }
        for sol in solutions:
            products_data = []
            channel = ''
            for prod in sol.products.order_by('order', 'platform', 'category'):
                sub = slack_subs.get((prod.id,))
                prod_channel = (sub.slack_channel or '') if sub else ''
                if not channel and prod_channel:
                    channel = prod_channel
                products_data.append({
                    'id': prod.id,
                    'label': f"{prod.get_platform_display()} {prod.get_category_display()}",
                    'active': sub.is_active if sub else False,
                })
            slack_solutions_data.append({
                'id': sol.id,
                'name': sol.name,
                'channel': channel,
                'products': products_data,
            })

    emails = list(customer.subscription_emails.order_by('id'))
    days_left = (tok.expires_at - timezone.now()).days

    return render(request, 'subscriber/subscribe.html', {
        'token': str(token),
        'customer': customer,
        'solutions': solutions_data,
        'utilities': utilities_data,
        'has_slack': has_slack,
        'slack_solutions': slack_solutions_data,
        'slack_utilities': slack_utilities_data,
        'emails': emails,
        'expires_at': tok.expires_at,
        'is_near_expiry': days_left <= 7,
    })


@csrf_exempt
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
                defaults={'is_active': True},
            )
            if not created and not obj.is_active:
                obj.is_active = True
                obj.save(update_fields=['is_active'])
    else:
        Subscription.objects.filter(
            customer=customer, product__solution=solution, channel=Subscription.CHANNEL_EMAIL,
        ).update(is_active=False)

    return JsonResponse({'ok': True})


@csrf_exempt
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


@csrf_exempt
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


@csrf_exempt
@require_POST
def subscribe_save_slack(request, token):
    tok = _get_valid_token(token)
    if not tok:
        return JsonResponse({'ok': False, 'error': '유효하지 않거나 만료된 링크입니다.'}, status=403)

    customer = tok.customer
    if not customer.slack_workspaces.filter(status='approved').exists():
        return JsonResponse({'ok': False, 'error': 'Slack 워크스페이스가 연동되어 있지 않습니다.'}, status=403)

    # 유틸리티 Slack 저장
    utility_id = request.POST.get('utility_id')
    if utility_id:
        channel = (request.POST.get('channel') or '').strip()
        is_active = request.POST.get('is_active') == 'true'
        try:
            utility = Utility.objects.get(pk=utility_id)
        except Utility.DoesNotExist:
            return JsonResponse({'ok': False, 'error': '유틸리티를 찾을 수 없습니다.'})
        obj, created = UtilitySubscription.objects.get_or_create(
            customer=customer, utility=utility,
            defaults={'is_active': is_active, 'slack_channel': channel},
        )
        if not created:
            update_fields = []
            if obj.is_active != is_active:
                obj.is_active = is_active
                update_fields.append('is_active')
            if obj.slack_channel != channel:
                obj.slack_channel = channel
                update_fields.append('slack_channel')
            if update_fields:
                obj.save(update_fields=update_fields)
        return JsonResponse({'ok': True})

    solution_id = request.POST.get('solution_id')
    channel = (request.POST.get('channel') or '').strip()
    active_ids = set(int(x) for x in request.POST.getlist('product_ids[]') if x.isdigit())

    from apps.product.models import Product
    solution_products = Product.objects.filter(
        solution_id=solution_id,
        solution__in=customer.solutions.all(),
    )
    for prod in solution_products:
        is_active = prod.id in active_ids
        sub, created = Subscription.objects.get_or_create(
            customer=customer, product=prod, channel=Subscription.CHANNEL_SLACK,
            defaults={'is_active': is_active, 'slack_channel': channel},
        )
        if not created:
            update_fields = []
            if sub.is_active != is_active:
                sub.is_active = is_active
                update_fields.append('is_active')
            if sub.slack_channel != channel:
                sub.slack_channel = channel
                update_fields.append('slack_channel')
            if update_fields:
                sub.save(update_fields=update_fields)

    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
def subscribe_toggle_utility(request, token):
    tok = _get_valid_token(token)
    if not tok:
        return JsonResponse({'ok': False, 'error': '유효하지 않거나 만료된 링크입니다.'}, status=403)

    utility_id = request.POST.get('utility_id')
    enabled = request.POST.get('enabled') == 'true'

    try:
        utility = Utility.objects.get(pk=utility_id)
    except Utility.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '유틸리티를 찾을 수 없습니다.'})

    obj, created = UtilitySubscription.objects.get_or_create(
        customer=tok.customer, utility=utility,
        defaults={'is_active': enabled},
    )
    if not created and obj.is_active != enabled:
        obj.is_active = enabled
        obj.save(update_fields=['is_active'])

    return JsonResponse({'ok': True})


def unsubscribe(request, token):
    """수신 거부 — 토큰에 해당하는 이메일 한 개만 비활성화"""
    from .models import SubscriptionEmail
    email_obj = get_object_or_404(SubscriptionEmail, unsubscribe_token=token)
    already_done = not email_obj.is_active
    if not already_done:
        email_obj.is_active = False
        email_obj.save(update_fields=['is_active'])
    return render(request, 'subscriber/unsubscribe.html', {
        'email': email_obj.email,
        'already_done': already_done,
    })

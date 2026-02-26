from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from web_project import TemplateLayout
from apps.customer.models import Customer
from .models import Subscription


class SubscriberManagementView(TemplateView):
    template_name = "subscriber/subscriber_management.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        customers = (
            Customer.objects
            .prefetch_related(
                'solutions',
                'subscriptions__solution',
            )
            .order_by('name')
        )

        # 테이블 표시용: 각 고객사의 Gmail/Slack 구독 솔루션 목록 첨부
        customer_rows = []
        for c in customers:
            subs = list(c.subscriptions.filter(is_active=True).select_related('solution'))
            email_subs = [s.solution.name for s in subs if s.channel == Subscription.CHANNEL_EMAIL]
            slack_subs = [s.solution.name for s in subs if s.channel == Subscription.CHANNEL_SLACK]
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
def get_customer_subscriptions(request, customer_id):
    """AJAX: 특정 고객사의 구매 솔루션 목록 + 기존 구독 설정 반환"""
    try:
        customer = Customer.objects.prefetch_related('solutions').get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'}, status=404)

    # 구매 솔루션만
    purchased_solutions = customer.solutions.order_by('name')

    # 기존 구독 매핑: {(solution_id, channel): Subscription}
    existing = {
        (s.solution_id, s.channel): s
        for s in Subscription.objects.filter(customer=customer).select_related('solution')
    }

    solutions_data = []
    for sol in purchased_solutions:
        email_sub = existing.get((sol.id, Subscription.CHANNEL_EMAIL))
        slack_sub = existing.get((sol.id, Subscription.CHANNEL_SLACK))
        solutions_data.append({
            'id': sol.id,
            'name': sol.name,
            'email': {
                'active': email_sub.is_active if email_sub else False,
                'frequency': email_sub.frequency if email_sub else Subscription.FREQUENCY_WEEKLY,
                'max_items': email_sub.max_items if email_sub else 5,
            },
            'slack': {
                'active': slack_sub.is_active if slack_sub else False,
                'frequency': slack_sub.frequency if slack_sub else Subscription.FREQUENCY_WEEKLY,
                'max_items': slack_sub.max_items if slack_sub else 5,
                'slack_channel': slack_sub.slack_channel or '' if slack_sub else '',
            },
        })

    return JsonResponse({
        'ok': True,
        'customer_name': customer.name,
        'solutions': solutions_data,
    })


@require_POST
def save_customer_subscription(request):
    """AJAX: 고객사+솔루션 단위 Gmail/Slack 구독 저장"""
    customer_id = request.POST.get('customer_id')
    solution_id = request.POST.get('solution_id')

    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '고객사를 찾을 수 없습니다.'})

    # 구매 솔루션 소유 여부 확인
    if not customer.solutions.filter(pk=solution_id).exists():
        return JsonResponse({'ok': False, 'error': '해당 솔루션의 구독 권한이 없습니다.'})

    from apps.product.models import Solution
    try:
        solution = Solution.objects.get(pk=solution_id)
    except Solution.DoesNotExist:
        return JsonResponse({'ok': False, 'error': '솔루션을 찾을 수 없습니다.'})

    # Gmail
    email_active = request.POST.get('email_active') == 'true'
    email_frequency = request.POST.get('email_frequency', Subscription.FREQUENCY_WEEKLY)
    email_max_items = int(request.POST.get('email_max_items', 5))

    if email_active:
        Subscription.objects.update_or_create(
            customer=customer,
            solution=solution,
            channel=Subscription.CHANNEL_EMAIL,
            defaults={
                'is_active': True,
                'frequency': email_frequency,
                'max_items': max(1, min(10, email_max_items)),
            },
        )
    else:
        Subscription.objects.filter(
            customer=customer, solution=solution, channel=Subscription.CHANNEL_EMAIL
        ).delete()

    # Slack
    slack_active = request.POST.get('slack_active') == 'true'
    slack_frequency = request.POST.get('slack_frequency', Subscription.FREQUENCY_WEEKLY)
    slack_max_items = int(request.POST.get('slack_max_items', 5))
    slack_channel = request.POST.get('slack_channel', '').strip()

    if slack_active:
        Subscription.objects.update_or_create(
            customer=customer,
            solution=solution,
            channel=Subscription.CHANNEL_SLACK,
            defaults={
                'is_active': True,
                'frequency': slack_frequency,
                'max_items': max(1, min(10, slack_max_items)),
                'slack_channel': slack_channel or None,
            },
        )
    else:
        Subscription.objects.filter(
            customer=customer, solution=solution, channel=Subscription.CHANNEL_SLACK
        ).delete()

    return JsonResponse({'ok': True, 'message': f'{solution.name} 구독 설정이 저장되었습니다.'})

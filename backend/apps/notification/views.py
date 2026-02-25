import json

from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from web_project import TemplateLayout
from apps.product.models import Solution
from apps.customer.models import Customer, CustomerEmail
from apps.logs.models import DispatchLog
from .models import OfficialNotice


class OfficialNoticeView(TemplateView):
    template_name = "notification/official_notice.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        solutions = Solution.objects.prefetch_related('customers__emails').order_by('name')

        solutions_data = []
        for sol in solutions:
            email_count = CustomerEmail.objects.filter(customer__solutions=sol).count()
            solutions_data.append({
                'id': sol.id,
                'name': sol.name,
                'customer_count': sol.customers.count(),
                'email_count': email_count,
            })

        context['solutions_data'] = solutions_data
        return context


@require_POST
def get_recipients_preview(request):
    """AJAX: 선택된 솔루션의 수신자 목록 반환"""
    solution_ids = request.POST.getlist('solution_ids[]')

    if not solution_ids:
        return JsonResponse({'recipients': [], 'count': 0})

    emails = (
        CustomerEmail.objects
        .filter(customer__solutions__id__in=solution_ids)
        .select_related('customer')
        .distinct()
        .order_by('customer__name', 'email')
    )

    recipients = [
        {
            'customer': e.customer.name,
            'email': e.email,
            'name': e.name or '',
        }
        for e in emails
    ]

    return JsonResponse({'recipients': recipients, 'count': len(recipients)})


@require_POST
def send_notice(request):
    """공문 발송"""
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    send_mode = request.POST.get('send_mode', 'direct')

    if not subject:
        return JsonResponse({'ok': False, 'error': '제목을 입력해주세요.'})
    if not body:
        return JsonResponse({'ok': False, 'error': '본문을 입력해주세요.'})

    if send_mode == 'solution':
        solution_ids = request.POST.getlist('solution_ids[]')
        if not solution_ids:
            return JsonResponse({'ok': False, 'error': '솔루션을 선택해주세요.'})
        emails = (
            CustomerEmail.objects
            .filter(customer__solutions__id__in=solution_ids)
            .select_related('customer')
            .distinct()
        )
        recipients = [
            {'customer': e.customer.name, 'customer_obj': e.customer, 'email': e.email, 'name': e.name or ''}
            for e in emails
        ]
    else:
        raw = request.POST.get('recipients_direct', '')
        email_list = [e.strip() for e in raw.replace(',', ';').split(';') if e.strip()]
        if not email_list:
            return JsonResponse({'ok': False, 'error': '수신 이메일을 입력해주세요.'})
        recipients = [{'customer': '', 'customer_obj': None, 'email': e, 'name': ''} for e in email_list]

    if not recipients:
        return JsonResponse({'ok': False, 'error': '수신자가 없습니다.'})

    now = timezone.now()
    recipients_for_json = [
        {'customer': r['customer'], 'email': r['email'], 'name': r['name']}
        for r in recipients
    ]

    notice = OfficialNotice.objects.create(
        subject=subject,
        body=body,
        send_mode=send_mode,
        recipients_json=json.dumps(recipients_for_json, ensure_ascii=False),
        recipient_count=len(recipients),
        sent_at=now,
    )

    # TODO: 실제 이메일 발송 구현
    # from django.core.mail import send_mass_mail
    # messages = [(subject, body, settings.DEFAULT_FROM_EMAIL, [r['email']]) for r in recipients]
    # send_mass_mail(messages, fail_silently=False)

    # 발송 로그 기록 (수신자별 1건)
    DispatchLog.objects.bulk_create([
        DispatchLog(
            log_type=DispatchLog.TYPE_OFFICIAL,
            channel=DispatchLog.CHANNEL_EMAIL,
            customer=r['customer_obj'],
            official_notice=notice,
            recipient=r['email'],
            subject=subject,
            status=DispatchLog.STATUS_SUCCESS,  # 실제 발송 구현 후 성공/실패 분기
            sent_at=now,
        )
        for r in recipients
    ])

    return JsonResponse({
        'ok': True,
        'message': f'{len(recipients)}명에게 공문을 발송했습니다.',
        'notice_id': notice.id,
    })

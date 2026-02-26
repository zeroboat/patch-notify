import json

from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from web_project import TemplateLayout
from apps.product.models import Solution
from apps.customer.models import Customer, CustomerEmail
from apps.logs.models import DispatchLog
from .models import OfficialNotice


def _send_official_email(to_email, subject, body_html):
    """Gmail SMTP로 공문 이메일 발송. (성공 여부, 에러 메시지) 반환"""
    try:
        html_body = render_to_string(
            'notification/email/official_notice_email.html',
            {'subject': subject, 'body': body_html},
        )
        text_body = strip_tags(body_html)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            to=[to_email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
        return True, ''
    except Exception as e:
        return False, str(e)


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

    # 수신자별 이메일 발송 + 로그 수집
    logs = []
    success_count = 0
    for r in recipients:
        ok, err = _send_official_email(r['email'], subject, body)
        if ok:
            success_count += 1
        logs.append(DispatchLog(
            log_type=DispatchLog.TYPE_OFFICIAL,
            channel=DispatchLog.CHANNEL_EMAIL,
            customer=r['customer_obj'],
            official_notice=notice,
            recipient=r['email'],
            subject=subject,
            status=DispatchLog.STATUS_SUCCESS if ok else DispatchLog.STATUS_FAILED,
            error_message=err,
            sent_at=now if ok else None,
        ))

    DispatchLog.objects.bulk_create(logs)

    failed_count = len(recipients) - success_count
    if success_count == 0:
        return JsonResponse({
            'ok': False,
            'error': f'발송에 실패했습니다. ({failed_count}건 실패)',
        })

    msg = f'{len(recipients)}명에게 발송 완료.'
    if failed_count:
        msg = f'{success_count}명 발송 완료, {failed_count}명 실패.'

    return JsonResponse({
        'ok': True,
        'message': msg,
        'notice_id': notice.id,
        'success_count': success_count,
        'failed_count': failed_count,
    })

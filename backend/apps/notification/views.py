import json
import logging
import traceback

from django.views.generic import TemplateView
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET

logger = logging.getLogger(__name__)
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.product.models import Solution
from apps.customer.models import Customer, CustomerEmail
from apps.logs.models import DispatchLog
from .models import OfficialNotice


def _send_official_email(to_emails, subject, body_html):
    """Gmail SMTP로 공문 이메일 발송. to_emails는 리스트. (성공 여부, 에러 메시지) 반환"""
    try:
        from django.core.mail import get_connection
        from apps.config.models import SiteConfig
        cfg = SiteConfig.get()

        html_body = render_to_string(
            'notification/email/official_notice_email.html',
            {'subject': subject, 'body': body_html},
        )
        text_body = strip_tags(body_html)

        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host='smtp.gmail.com',
            port=587,
            use_tls=True,
            username=cfg.gmail_user,
            password=cfg.gmail_app_password,
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=cfg.gmail_user,
            to=to_emails,
            connection=connection,
        )
        msg.attach_alternative(html_body, 'text/html')
        sent = msg.send(fail_silently=False)
        if sent == 0:
            return False, '발송 서버가 메시지를 거부했습니다 (sent=0).'
        return True, ''
    except Exception as e:
        err_detail = traceback.format_exc()
        logger.error("이메일 발송 실패 to=%s\n%s", to_emails, err_detail)
        return False, f"{type(e).__name__}: {e}"


class OfficialNoticeView(RoleRequiredMixin, TemplateView):
    """Admin 전용: 공문 작성 및 발송"""
    allowed_roles = []
    template_name = "notification/official_notice.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        solutions = Solution.objects.prefetch_related('customers__emails').order_by('order', 'id')

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
@role_required()
def preview_email(request):
    """이메일 본문 미리보기 — 실제 이메일 템플릿으로 렌더링해서 HTML 반환"""
    subject = request.POST.get('subject', '(제목 없음)').strip() or '(제목 없음)'
    body = request.POST.get('body', '').strip()
    html = render_to_string(
        'notification/email/official_notice_email.html',
        {'subject': subject, 'body': body},
    )
    return HttpResponse(html)


@require_POST
@role_required()
def get_recipients_preview(request):
    """Admin 전용 AJAX: 선택된 솔루션의 수신자 목록 반환"""
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
@role_required()
def send_notice(request):
    """Admin 전용: 공문 발송"""
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    send_mode = request.POST.get('send_mode', 'direct')

    if not subject:
        return JsonResponse({'ok': False, 'error': '제목을 입력해주세요.'})
    if not body:
        return JsonResponse({'ok': False, 'error': '본문을 입력해주세요.'})

    # ── 수신 그룹 구성 (고객사별 묶음) ─────────────────────────
    # groups: [{'customer': obj_or_None, 'customer_name': str, 'emails': [str, ...]}]
    if send_mode == 'solution':
        solution_ids = request.POST.getlist('solution_ids[]')
        if not solution_ids:
            return JsonResponse({'ok': False, 'error': '솔루션을 선택해주세요.'})

        email_qs = (
            CustomerEmail.objects
            .filter(customer__solutions__id__in=solution_ids)
            .select_related('customer')
            .distinct()
            .order_by('customer__name', 'email')
        )

        # 고객사별로 묶기
        customer_map = {}
        for e in email_qs:
            cid = e.customer_id
            if cid not in customer_map:
                customer_map[cid] = {'customer': e.customer, 'customer_name': e.customer.name, 'emails': []}
            customer_map[cid]['emails'].append(e.email)
        groups = list(customer_map.values())

    else:
        raw = request.POST.get('recipients_direct', '')
        email_list = [e.strip() for e in raw.replace(',', ';').split(';') if e.strip()]
        if not email_list:
            return JsonResponse({'ok': False, 'error': '수신 이메일을 입력해주세요.'})
        # direct 모드는 고객사 구분 없이 단일 그룹으로 발송
        groups = [{'customer': None, 'customer_name': '', 'emails': email_list}]

    if not groups:
        return JsonResponse({'ok': False, 'error': '수신자가 없습니다.'})

    now = timezone.now()
    total_emails = sum(len(g['emails']) for g in groups)
    recipients_for_json = [
        {'customer': g['customer_name'], 'emails': g['emails']}
        for g in groups
    ]

    notice = OfficialNotice.objects.create(
        subject=subject,
        body=body,
        send_mode=send_mode,
        recipients_json=json.dumps(recipients_for_json, ensure_ascii=False),
        recipient_count=total_emails,
        sent_at=now,
    )

    # 고객사별 발송 + 로그 수집
    logs = []
    success_count = 0
    for g in groups:
        ok, err = _send_official_email(g['emails'], subject, body)
        if ok:
            success_count += 1
        logs.append(DispatchLog(
            log_type=DispatchLog.TYPE_OFFICIAL,
            channel=DispatchLog.CHANNEL_EMAIL,
            customer=g['customer'],
            official_notice=notice,
            recipient=', '.join(g['emails']),
            subject=subject,
            status=DispatchLog.STATUS_SUCCESS if ok else DispatchLog.STATUS_FAILED,
            error_message=err,
            sent_at=now,
        ))

    DispatchLog.objects.bulk_create(logs)

    failed_count = len(groups) - success_count
    if success_count == 0:
        return JsonResponse({
            'ok': False,
            'error': f'발송에 실패했습니다. ({failed_count}개 고객사 실패)',
        })

    msg = f'{len(groups)}개 고객사 ({total_emails}명)에게 발송 완료.'
    if failed_count:
        msg = f'{success_count}개 고객사 발송 완료, {failed_count}개 실패.'

    return JsonResponse({
        'ok': True,
        'message': msg,
        'notice_id': notice.id,
        'success_count': success_count,
        'failed_count': failed_count,
    })


@require_GET
@role_required('se')
def view_notice(request, notice_id):
    """발송 이력에서 공문 원문 조회 — 렌더링된 이메일 HTML 반환"""
    notice = get_object_or_404(OfficialNotice, pk=notice_id)
    html = render_to_string(
        'notification/email/official_notice_email.html',
        {'subject': notice.subject, 'body': notice.body},
    )
    return HttpResponse(html)

import base64
import json
import logging
import os
import traceback
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import smtplib

from django.conf import settings
from django.views.generic import TemplateView
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from web_project import TemplateLayout
from apps.base.mixins import RoleRequiredMixin, role_required
from apps.product.models import Solution, Product, Utility
from apps.patchnote.models import PatchNote
from apps.customer.models import Customer, CustomerEmail
from apps.logs.models import DispatchLog
from .models import OfficialNotice, NoticeConfig
from apps.logs.models import ActionLog


# ── 이미지 헬퍼 ────────────────────────────────────────────────────────────────

def _read_logo(logo_field):
    """ImageField 또는 로컬 파일 경로에서 바이너리 읽기. 없으면 None."""
    if not logo_field:
        return None
    try:
        path = os.path.join(settings.MEDIA_ROOT, str(logo_field))
        with open(path, 'rb') as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return None


def _to_b64(data, mime='image/png'):
    if not data:
        return ''
    return f'data:{mime};base64,' + base64.b64encode(data).decode()


def _build_template_context(subject, body_html, *, for_email=False):
    """이메일/미리보기 공통 컨텍스트. for_email=True 이면 CID, False 이면 Base64."""
    cfg = NoticeConfig.get()
    upper_data = _read_logo(cfg.upper_logo)
    lower_data = _read_logo(cfg.lower_logo)

    if for_email:
        upper_src = 'cid:upper_logo' if upper_data else ''
        lower_src = 'cid:lower_logo' if lower_data else ''
    else:
        upper_src = _to_b64(upper_data)
        lower_src = _to_b64(lower_data)

    return {
        'subject': subject,
        'body': body_html,
        'upper_logo_src': upper_src,
        'upper_logo_width': cfg.upper_logo_width,
        'lower_logo_src': lower_src,
        'lower_logo_width': cfg.lower_logo_width,
        'header_color': cfg.header_color,
        'footer_text': cfg.footer_text,
        '_upper_data': upper_data,
        '_lower_data': lower_data,
    }


# ── 이메일 발송 ────────────────────────────────────────────────────────────────

def _send_official_email(to_emails, subject, body_html, unsubscribe_url=''):
    """Gmail SMTP로 공문 이메일 발송. (성공 여부, 에러 메시지) 반환"""
    try:
        from apps.config.models import SiteConfig
        site = SiteConfig.get()

        ctx = _build_template_context(subject, body_html, for_email=True)
        ctx['unsubscribe_url'] = unsubscribe_url
        html_body = render_to_string('notification/email/official_notice_email.html', ctx)
        text_body = strip_tags(body_html)

        msg_related = MIMEMultipart('related')
        msg_alternative = MIMEMultipart('alternative')
        msg_alternative.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg_related.attach(msg_alternative)

        for cid, data in [('upper_logo', ctx['_upper_data']), ('lower_logo', ctx['_lower_data'])]:
            if data:
                img = MIMEImage(data)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline')
                msg_related.attach(img)

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = site.gmail_user
        msg['To'] = ', '.join(to_emails)
        msg.attach(msg_related)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()
            server.starttls()
            server.login(site.gmail_user, site.gmail_app_password)
            server.sendmail(site.gmail_user, to_emails, msg.as_string())

        return True, ''
    except Exception as e:
        logger.error("이메일 발송 실패 to=%s\n%s", to_emails, traceback.format_exc())
        return False, f"{type(e).__name__}: {e}"


# ── 공문 작성 뷰 ───────────────────────────────────────────────────────────────

class OfficialNoticeView(RoleRequiredMixin, TemplateView):
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


# ── Notice 템플릿 설정 뷰 ───────────────────────────────────────────────────────

class NoticeConfigView(RoleRequiredMixin, TemplateView):
    allowed_roles = ['admin', 'manager']
    template_name = "notification/notice_config.html"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['cfg'] = NoticeConfig.get()
        return context

    def post(self, request, *args, **kwargs):
        cfg = NoticeConfig.get()

        cfg.upper_logo_width = int(request.POST.get('upper_logo_width') or cfg.upper_logo_width)
        cfg.lower_logo_width = int(request.POST.get('lower_logo_width') or cfg.lower_logo_width)
        cfg.header_color = request.POST.get('header_color', cfg.header_color).strip() or cfg.header_color
        cfg.footer_text = request.POST.get('footer_text', cfg.footer_text)
        email_subject_prefix = request.POST.get('email_subject_prefix', '').strip()
        if email_subject_prefix:
            cfg.email_subject_prefix = email_subject_prefix
        patchnote_title_format = request.POST.get('patchnote_title_format', '').strip()
        if patchnote_title_format:
            cfg.patchnote_title_format = patchnote_title_format

        if 'upper_logo' in request.FILES:
            if cfg.upper_logo:
                cfg.upper_logo.delete(save=False)
            cfg.upper_logo = request.FILES['upper_logo']

        if 'lower_logo' in request.FILES:
            if cfg.lower_logo:
                cfg.lower_logo.delete(save=False)
            cfg.lower_logo = request.FILES['lower_logo']

        if request.POST.get('clear_upper_logo') == '1':
            if cfg.upper_logo:
                cfg.upper_logo.delete(save=False)
            cfg.upper_logo = None

        if request.POST.get('clear_lower_logo') == '1':
            if cfg.lower_logo:
                cfg.lower_logo.delete(save=False)
            cfg.lower_logo = None

        cfg.save()
        ActionLog.record(request, ActionLog.NOTICE_CONFIG_UPDATE, '공문 템플릿 설정')
        return JsonResponse({'ok': True})


# ── AJAX ───────────────────────────────────────────────────────────────────────

@require_POST
@role_required()
def preview_email(request):
    subject = request.POST.get('subject', '(제목 없음)').strip() or '(제목 없음)'
    body = request.POST.get('body', '').strip()
    ctx = _build_template_context(subject, body, for_email=False)
    ctx['unsubscribe_url'] = '#'
    html = render_to_string('notification/email/official_notice_email.html', ctx)
    return HttpResponse(html)


@require_POST
@role_required()
def preview_patchnote_email(request):
    """패치노트 구독 이메일 미리보기 — patchnote_id 있으면 실제 데이터, 없으면 샘플"""
    patchnote_id = request.POST.get('patchnote_id', '').strip()

    preview_version = ''
    if patchnote_id:
        note = get_object_or_404(
            PatchNote.objects.select_related('product__solution', 'utility')
            .prefetch_related('features', 'improvements', 'bugfixes', 'remarks'),
            pk=patchnote_id,
        )
        product_label = str(note.product) if note.product else note.utility.name
        preview_version = note.version
        notes_data = [{
            'note': note,
            'is_new': True,
            'features':     list(note.features.filter(parent__isnull=True).order_by('order', 'id')),
            'improvements': list(note.improvements.filter(parent__isnull=True).order_by('order', 'id')),
            'bugfixes':     list(note.bugfixes.filter(parent__isnull=True).order_by('order', 'id')),
            'remarks':      list(note.remarks.filter(parent__isnull=True).order_by('order', 'id')),
        }]
    else:
        first_note = (
            PatchNote.objects
            .select_related('product__solution', 'utility')
            .prefetch_related('features', 'improvements', 'bugfixes', 'remarks')
            .order_by('-release_date', '-id')
            .first()
        )
        if first_note:
            product_label = str(first_note.product) if first_note.product else first_note.utility.name
            preview_version = first_note.version
            notes_data = [{
                'note': first_note,
                'is_new': True,
                'features':     list(first_note.features.filter(parent__isnull=True).order_by('order', 'id')),
                'improvements': list(first_note.improvements.filter(parent__isnull=True).order_by('order', 'id')),
                'bugfixes':     list(first_note.bugfixes.filter(parent__isnull=True).order_by('order', 'id')),
                'remarks':      list(first_note.remarks.filter(parent__isnull=True).order_by('order', 'id')),
            }]
        else:
            from types import SimpleNamespace

            def _item(text):
                return SimpleNamespace(content=f'<p style="margin:0 0 4px 0;">• {text}</p>')

            product_label = '제품명 Platform Category'
            preview_version = '1.0.0'
            notes_data = [{
                'note': SimpleNamespace(version='1.0.0', release_date='-'),
                'is_new': True,
                'features':     [_item('신규 기능 추가')],
                'improvements': [_item('성능 개선')],
                'bugfixes':     [_item('버그 수정')],
                'remarks':      [],
            }]

    cfg = NoticeConfig.get()
    fmt = cfg.patchnote_title_format or '{product} Release 안내'
    ctx = _build_template_context('', '', for_email=False)
    ctx['product_label'] = fmt.replace('{product}', product_label).replace('{version}', preview_version)
    ctx['notes_data'] = notes_data
    ctx['unsubscribe_url'] = '#'

    html = render_to_string('patchnote/email/patchnote_notification_email.html', ctx)
    return HttpResponse(html)


@require_GET
@role_required()
def get_products_for_preview(request):
    """미리보기용 제품+유틸리티 목록"""
    products = (
        Product.objects
        .select_related('solution')
        .filter(patch_notes__isnull=False)
        .distinct()
        .order_by('solution__order', 'solution__id', 'order', 'id')
    )
    data = [{'id': f'p_{p.id}', 'label': str(p)} for p in products]

    utilities = (
        Utility.objects
        .filter(patch_notes__isnull=False)
        .distinct()
        .order_by('name')
    )
    data += [{'id': f'u_{u.id}', 'label': u.name} for u in utilities]

    return JsonResponse({'products': data})


@require_GET
@role_required()
def get_versions_for_preview(request):
    """특정 제품/유틸리티의 패치노트 버전 목록"""
    product_key = request.GET.get('product_key', '')
    if product_key.startswith('p_'):
        notes = (
            PatchNote.objects
            .filter(product_id=product_key[2:])
            .order_by('-release_date', '-id')
            .values('id', 'version', 'release_date', 'is_published')
        )
    elif product_key.startswith('u_'):
        notes = (
            PatchNote.objects
            .filter(utility_id=product_key[2:])
            .order_by('-release_date', '-id')
            .values('id', 'version', 'release_date', 'is_published')
        )
    else:
        return JsonResponse({'versions': []})

    data = [
        {
            'id': n['id'],
            'label': f"v{n['version']} ({n['release_date']}) {'✓' if n['is_published'] else '미발행'}",
        }
        for n in notes
    ]
    return JsonResponse({'versions': data})


@require_POST
@role_required()
def get_recipients_preview(request):
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
        {'customer': e.customer.name, 'email': e.email, 'name': e.name or ''}
        for e in emails
    ]
    return JsonResponse({'recipients': recipients, 'count': len(recipients)})


@require_POST
@role_required()
def send_notice(request):
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    send_mode = request.POST.get('send_mode', 'direct')

    if not subject:
        return JsonResponse({'ok': False, 'error': '제목을 입력해주세요.'})
    if not body:
        return JsonResponse({'ok': False, 'error': '본문을 입력해주세요.'})

    from django.contrib.sites.models import Site
    from django.urls import reverse
    try:
        _site = Site.objects.get_current()
        _base_url = f"https://{_site.domain}"
    except Exception:
        _base_url = ''

    if send_mode == 'solution':
        solution_ids = request.POST.getlist('solution_ids[]')
        if not solution_ids:
            return JsonResponse({'ok': False, 'error': '솔루션을 선택해주세요.'})
        email_qs = (
            CustomerEmail.objects
            .filter(customer__solutions__id__in=solution_ids, is_active=True)
            .select_related('customer')
            .distinct()
            .order_by('customer__name', 'email')
        )
        customer_map = {}
        for e in email_qs:
            cid = e.customer_id
            if cid not in customer_map:
                customer_map[cid] = {'customer': e.customer, 'customer_name': e.customer.name, 'email_objs': []}
            customer_map[cid]['email_objs'].append(e)
        groups = list(customer_map.values())
    else:
        raw = request.POST.get('recipients_direct', '')
        email_list = [e.strip() for e in raw.replace(',', ';').split(';') if e.strip()]
        if not email_list:
            return JsonResponse({'ok': False, 'error': '수신 이메일을 입력해주세요.'})
        groups = [{'customer': None, 'customer_name': '', 'email_objs': None, 'emails_direct': email_list}]

    if not groups:
        return JsonResponse({'ok': False, 'error': '수신자가 없습니다.'})

    now = timezone.now()
    total_emails = sum(
        len(g.get('email_objs') or g.get('emails_direct', [])) for g in groups
    )
    notice = OfficialNotice.objects.create(
        subject=subject,
        body=body,
        send_mode=send_mode,
        recipients_json=json.dumps(
            [{'customer': g['customer_name'],
              'emails': [e.email for e in g['email_objs']] if g.get('email_objs') else g.get('emails_direct', [])}
             for g in groups],
            ensure_ascii=False,
        ),
        recipient_count=total_emails,
        sent_at=now,
    )

    logs = []
    success_count = 0
    for g in groups:
        if g.get('email_objs'):
            for email_obj in g['email_objs']:
                _unsub_path = reverse('customer:unsubscribe_notice', args=[email_obj.unsubscribe_token])
                _unsub_url = f"{_base_url}{_unsub_path}"
                ok, err = _send_official_email([email_obj.email], subject, body, unsubscribe_url=_unsub_url)
                if ok:
                    success_count += 1
                logs.append(DispatchLog(
                    log_type=DispatchLog.TYPE_OFFICIAL,
                    channel=DispatchLog.CHANNEL_EMAIL,
                    customer=g['customer'],
                    official_notice=notice,
                    recipient=email_obj.email,
                    subject=subject,
                    status=DispatchLog.STATUS_SUCCESS if ok else DispatchLog.STATUS_FAILED,
                    error_message=err,
                    sent_at=now,
                ))
        else:
            ok, err = _send_official_email(g.get('emails_direct', []), subject, body)
            if ok:
                success_count += 1
            logs.append(DispatchLog(
                log_type=DispatchLog.TYPE_OFFICIAL,
                channel=DispatchLog.CHANNEL_EMAIL,
                customer=g['customer'],
                official_notice=notice,
                recipient=', '.join(g.get('emails_direct', [])),
                subject=subject,
                status=DispatchLog.STATUS_SUCCESS if ok else DispatchLog.STATUS_FAILED,
                error_message=err,
                sent_at=now,
            ))

    DispatchLog.objects.bulk_create(logs)

    failed_count = len(groups) - success_count
    if success_count == 0:
        ActionLog.record(request, ActionLog.NOTICE_SEND, subject, {
            '결과': '전체 실패', '고객사 수': len(groups), '수신자 수': total_emails,
        })
        return JsonResponse({'ok': False, 'error': f'발송에 실패했습니다. ({failed_count}개 고객사 실패)'})

    msg = f'{len(groups)}개 고객사 ({total_emails}명)에게 발송 완료.'
    if failed_count:
        msg = f'{success_count}개 고객사 발송 완료, {failed_count}개 실패.'

    ActionLog.record(request, ActionLog.NOTICE_SEND, subject, {
        '결과': f'{success_count}성공 / {failed_count}실패',
        '고객사 수': len(groups),
        '수신자 수': total_emails,
    })
    return JsonResponse({
        'ok': True, 'message': msg, 'notice_id': notice.id,
        'success_count': success_count, 'failed_count': failed_count,
    })


@require_GET
@role_required('se')
def view_notice(request, notice_id):
    notice = get_object_or_404(OfficialNotice, pk=notice_id)
    html = render_to_string(
        'notification/email/official_notice_email.html',
        _build_template_context(notice.subject, notice.body, for_email=False),
    )
    return HttpResponse(html)

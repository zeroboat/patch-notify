import logging
import re
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import TemplateView

from web_project import TemplateLayout
from apps.base.mixins import role_required, get_user_role
from apps.product.models import Product
from .models import PatchNote, Feature, Improvement, BugFix, Remark, Internal, PatchNoteFile
from .nextcloud import upload_to_nextcloud, create_share_link, delete_from_nextcloud
from .translation import start_translation

logger = logging.getLogger(__name__)


def _html_to_plain(html: str) -> str:
    """HTML → 줄바꿈 보존 plain text (Slack mrkdwn용, <ul> 깊이 기반 들여쓰기)"""
    if not html:
        return ''
    # bold / code 먼저 변환
    html = re.sub(r'<(strong|b)[^>]*>(.+?)</(strong|b)>', r'*\2*', html, flags=re.DOTALL)
    html = re.sub(r'<code[^>]*>(.+?)</code>', r'`\1`', html, flags=re.DOTALL)

    result = []
    ul_depth = 0
    for token in re.split(r'(</?[a-zA-Z][^>]*>)', html):
        if not token:
            continue
        m = re.match(r'^<(/?)(\w+)', token)
        if m:
            closing, tag = m.group(1), m.group(2).lower()
            if tag in ('ul', 'ol'):
                ul_depth = max(0, ul_depth + (-1 if closing else 1))
            elif tag == 'li' and not closing:
                result.append(f'\n{"  " * ul_depth}- ')
            elif tag == 'br':
                result.append('\n')
            elif tag in ('p', 'div') and closing:
                result.append('\n')
            # 나머지 태그 무시
        else:
            token = token.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            result.append(token)

    text = re.sub(r'\n{3,}', '\n\n', ''.join(result))
    return text.lstrip('\n').rstrip()


def _build_patchnote_slack_blocks(patch_note, *, include_internal: bool = False) -> list:
    """단일 패치노트를 Slack Block Kit 블록으로 변환

    include_internal=True 일 경우 [Internal] 섹션을 본문에 추가 (사내 발송 전용).
    """
    def _section_text(manager):
        obj = manager.filter(parent__isnull=True).order_by('order', 'id').first()
        if not obj or not obj.content:
            return '  - N/A'
        return _html_to_plain(obj.content) or '  - N/A'

    features_text   = _section_text(patch_note.features)
    improvements_text = _section_text(patch_note.improvements)
    bugfixes_text   = _section_text(patch_note.bugfixes)

    body = (
        f"[Patch Note]\n"
        f"기능 추가\n{features_text}\n\n"
        f"기능 개선\n{improvements_text}\n\n"
        f"버그 수정\n{bugfixes_text}"
    )

    remarks_obj = patch_note.remarks.filter(parent__isnull=True).order_by('order', 'id').first()
    if remarks_obj and remarks_obj.content:
        remarks_text = _html_to_plain(remarks_obj.content)
        if remarks_text:
            body += f"\n\n[Remarks]\n{remarks_text}"

    if include_internal:
        internal_obj = patch_note.internals.filter(parent__isnull=True).order_by('order', 'id').first()
        if internal_obj and internal_obj.content:
            internal_text = _html_to_plain(internal_obj.content)
            if internal_text:
                body += f"\n\n[Internal · 사내 공유 전용]\n{internal_text}"

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Version: {patch_note.version}*  ·  {patch_note.release_date}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{body}```"},
        },
        {"type": "divider"},
    ]


def _send_internal_slack_notification(patch_note):
    """발행 시 사내 구독 채널에 패치노트 전송 (Internal 항목 포함, 즉시)"""
    try:
        from apps.config.models import SiteConfig
        from apps.slack_app.models import SlackWorkspace
        from apps.subscriber.models import Subscription
        from slack_sdk import WebClient

        if not SiteConfig.get().internal_slack_enabled:
            return

        internal_workspace = SlackWorkspace.objects.filter(
            is_internal=True,
            status=SlackWorkspace.STATUS_APPROVED,
        ).first()
        if not internal_workspace:
            logger.warning('사내 Slack 워크스페이스 미설정 — Admin에서 is_internal 체크 필요')
            return

        subs = (
            Subscription.objects
            .filter(
                product=patch_note.product,
                channel=Subscription.CHANNEL_SLACK,
                is_active=True,
                slack_channel__isnull=False,
                customer=internal_workspace.customer,
            )
            .exclude(slack_channel='')
        )

        if not subs.exists():
            return

        solution_name = patch_note.product.solution.name
        platform = patch_note.product.get_platform_display()
        category = patch_note.product.get_category_display()
        product_label = f"{solution_name} {platform} {category}"

        for sub in subs:
            recent_notes = (
                PatchNote.objects
                .filter(product=patch_note.product, is_published=True)
                .prefetch_related('features', 'improvements', 'bugfixes', 'remarks', 'internals')
                .order_by('-release_date', '-version')
                [:sub.max_items]
            )

            blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"[INTERNAL] [{product_label} Release 안내]"}}]
            prev_header_added = False
            for note in recent_notes:
                if note.id != patch_note.id and not prev_header_added:
                    blocks.append({"type": "header", "text": {"type": "plain_text", "text": f"[{product_label} 이전 패치노트]"}})
                    prev_header_added = True
                blocks.extend(_build_patchnote_slack_blocks(note, include_internal=True))

            fallback_text = f"[사내] {product_label} v{patch_note.version} 패치노트가 발행되었습니다."

            try:
                client = WebClient(token=internal_workspace.bot_token)
                client.chat_postMessage(
                    channel=sub.slack_channel,
                    text=fallback_text,
                    blocks=blocks,
                )
            except Exception as e:
                logger.warning(f'사내 Slack 알림 실패 (channel={sub.slack_channel}): {e}')
    except Exception as e:
        logger.warning(f'사내 Slack 알림 처리 실패: {e}')


def _send_slack_notifications(patch_note):
    """발행 시 활성 Slack 구독자에게 최근 max_items건 패치노트 전송 (고객사용)"""
    try:
        from slack_sdk import WebClient
        from apps.slack_app.models import SlackWorkspace
        from apps.subscriber.models import Subscription

        subs = (
            Subscription.objects
            .filter(
                product=patch_note.product,
                channel=Subscription.CHANNEL_SLACK,
                is_active=True,
                slack_channel__isnull=False,
            )
            .exclude(slack_channel='')
            .select_related('customer')
        )

        if not subs.exists():
            return

        solution_name = patch_note.product.solution.name
        platform = patch_note.product.get_platform_display()
        category = patch_note.product.get_category_display()
        product_label = f"{solution_name} {platform} {category}"

        for sub in subs:
            workspace = SlackWorkspace.objects.filter(
                customer=sub.customer,
                status=SlackWorkspace.STATUS_APPROVED,
                is_internal=False,
            ).first()
            if not workspace:
                continue

            # 구독자별 max_items건 조회
            recent_notes = (
                PatchNote.objects
                .filter(product=patch_note.product, is_published=True)
                .prefetch_related('features', 'improvements', 'bugfixes', 'remarks')
                .order_by('-release_date', '-version')
                [:sub.max_items]
            )

            blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"[{product_label} Release 안내]"}}]
            prev_header_added = False
            for note in recent_notes:
                if note.id != patch_note.id and not prev_header_added:
                    blocks.append({"type": "header", "text": {"type": "plain_text", "text": f"[{product_label} 이전 패치노트]"}})
                    prev_header_added = True
                blocks.extend(_build_patchnote_slack_blocks(note))

            fallback_text = f"{product_label} v{patch_note.version} 패치노트가 발행되었습니다."

            try:
                client = WebClient(token=workspace.bot_token)
                client.chat_postMessage(
                    channel=sub.slack_channel,
                    text=fallback_text,
                    blocks=blocks,
                )
            except Exception as e:
                logger.warning(f'Slack 알림 실패 (customer={sub.customer.name}): {e}')
    except Exception as e:
        logger.warning(f'Slack 알림 처리 실패: {e}')


def _push_to_notion_safe(patch_note, is_new=None):
    """Notion push를 시도하되, 실패해도 DB 저장에는 영향 없게 처리.

    is_new=None이면 notion_pushed_at 유무로 자동 판단:
      - 이미 push된 적 있으면 Update(False), 없으면 Insert(True)
    """
    from apps.config.models import SiteConfig
    if not SiteConfig.get().notion_enabled:
        return
    if is_new is None:
        is_new = patch_note.notion_pushed_at is None
    try:
        from apps.notion.services import push_patch_note_to_notion
        push_patch_note_to_notion(patch_note, is_new=is_new)
        patch_note.notion_pushed_at = timezone.now()
        patch_note.save(update_fields=['notion_pushed_at'])
    except Exception as e:
        logger.warning(f'Notion push 실패 (v{patch_note.version}): {e}')


# ──────────────────────────────────────────────
# 외부 발송 지연 처리 (Django-Q2 워커가 호출)
# ──────────────────────────────────────────────

def dispatch_external_notifications(patch_note_id: int):
    """[Q2 Task] 예약 시각에 도달했을 때 외부(고객사 Slack/Gmail) 발송 실행.

    워커 프로세스가 import 가능해야 하므로 모듈 최상위 함수로 정의.
    호출 시점에 DB 상태를 다시 읽어 상태가 'pending'이 아니면 skip (취소/중복 방지).
    """
    try:
        note = (
            PatchNote.objects
            .select_related('product__solution')
            .prefetch_related('features', 'improvements', 'bugfixes', 'remarks')
            .get(id=patch_note_id)
        )
    except PatchNote.DoesNotExist:
        logger.warning(f'외부 발송 task: 패치노트 없음 (id={patch_note_id})')
        return

    if note.external_send_status != PatchNote.EXTERNAL_SEND_PENDING:
        logger.info(
            f'외부 발송 task: 상태가 pending 아님 (id={patch_note_id}, '
            f'status={note.external_send_status}) — skip'
        )
        return

    try:
        _send_slack_notifications(note)
        # TODO: Gmail 발송 함수가 별도 존재한다면 여기서 호출
        note.external_send_status = PatchNote.EXTERNAL_SEND_SENT
        note.external_send_error = ''
        note.save(update_fields=['external_send_status', 'external_send_error', 'updated_at'])
    except Exception as e:
        logger.exception(f'외부 발송 task 실패 (id={patch_note_id})')
        note.external_send_status = PatchNote.EXTERNAL_SEND_FAILED
        note.external_send_error = str(e)[:1000]
        note.save(update_fields=['external_send_status', 'external_send_error', 'updated_at'])


def _schedule_external_send(note):
    """발행 시 호출 — 지연 시간에 맞춰 Q2 task 등록.
    delay=0 이면 즉시 실행되도록 task 큐에 넣음 (워커가 처리)."""
    from apps.config.models import SiteConfig
    from django_q.tasks import async_task, schedule
    from django_q.models import Schedule

    delay_minutes = SiteConfig.get().external_send_delay_minutes or 0
    scheduled_at = timezone.now() + timedelta(minutes=delay_minutes)

    note.external_send_scheduled_at = scheduled_at
    note.external_send_status = PatchNote.EXTERNAL_SEND_PENDING
    note.external_send_error = ''

    if delay_minutes <= 0:
        # 즉시 실행 — 워커에 바로 큐잉
        task_id = async_task(
            'apps.patchnote.views.dispatch_external_notifications',
            note.id,
            task_name=f'patchnote-extsend-{note.id}',
        )
        note.external_send_task_id = task_id or ''
    else:
        # 지연 실행 — Schedule 1회성 등록
        sched = schedule(
            'apps.patchnote.views.dispatch_external_notifications',
            note.id,
            schedule_type=Schedule.ONCE,
            next_run=scheduled_at,
            name=f'patchnote-extsend-{note.id}',
            repeats=-1,
        )
        note.external_send_task_id = str(sched.id) if sched else ''

    note.save(update_fields=[
        'external_send_scheduled_at',
        'external_send_status',
        'external_send_task_id',
        'external_send_error',
        'updated_at',
    ])


class PatchNoteDetailView(LoginRequiredMixin, TemplateView):
    template_name = "patchnote/patch_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)

        product_id = self.kwargs.get('product_id')
        product = get_object_or_404(Product, id=product_id)

        patch_notes = PatchNote.objects.filter(product=product).prefetch_related(
            'features', 'improvements', 'bugfixes', 'remarks', 'internals', 'files'
        ).order_by('-release_date', '-version')

        context.update({
            'selected_product': product,
            'patch_notes': patch_notes,
        })
        return context


# ──────────────────────────────────────────────
# 헬퍼: 섹션 HTML 저장 / 조회
# ──────────────────────────────────────────────

def _save_section(patch_note, html, model_class):
    """CKEditor HTML을 섹션당 1개 레코드로 저장 (실제 텍스트 없으면 건너뜀)"""
    html = (html or '').strip()
    if not html:
        return
    # 내용이 없는 <p> 태그 먼저 제거 (<p>&nbsp;</p>, <p><br></p> 등)
    html = re.sub(r'<p(?=\s|>)[^>]*>(\s|&nbsp;|<br\s*/?>)*</p>', '', html)
    # <p> 태그 제거 (내용은 유지, <pre> 등은 건드리지 않음)
    html = re.sub(r'<p(?=\s|>)[^>]*>', '', html)
    html = re.sub(r'</p>', '', html)
    html = html.strip()
    # 태그 제거 후 텍스트가 없으면 저장 안 함 (&nbsp; 엔티티 문자열도 함께 처리)
    text_only = re.sub(r'<[^>]+>', '', html).replace('\xa0', '').replace('&nbsp;', '').strip()
    if not text_only:
        return
    model_class.objects.create(patch_note=patch_note, content=html, order=0)


def _get_section_html(manager):
    """섹션의 저장된 HTML 반환 (수정 모달용)"""
    obj = manager.filter(parent__isnull=True).order_by('order', 'id').first()
    return obj.content if obj else ''


# ──────────────────────────────────────────────
# 패치노트 등록 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_append(request):
    print(request.POST)  # 디버깅용 로그
    try:
        product_id  = request.POST.get('product_id', '').strip()
        version     = request.POST.get('version', '').strip()
        patch_date  = request.POST.get('patch_date', '').strip()

        new_features_html    = request.POST.get('new_features', '')
        improvements_html    = request.POST.get('improvements', '')
        bug_fixes_html       = request.POST.get('bug_fixes', '')
        special_notes_html   = request.POST.get('special_notes', '')
        internal_notes_html  = request.POST.get('internal_notes', '')

        if not product_id:
            return JsonResponse({'error': '제품 정보가 누락되었습니다.'}, status=400)
        if not version:
            return JsonResponse({'error': '버전을 입력해주세요.'}, status=400)
        if not patch_date:
            return JsonResponse({'error': '배포 날짜를 입력해주세요.'}, status=400)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return JsonResponse({'error': '제품을 찾을 수 없습니다.'}, status=400)

        patch_note, created = PatchNote.objects.get_or_create(
            product=product,
            version=version,
            defaults={'release_date': patch_date},
        )
        if not created:
            return JsonResponse(
                {'error': f'버전 {version}은 이미 등록되어 있습니다.'},
                status=400,
            )

        _save_section(patch_note, new_features_html,  Feature)
        _save_section(patch_note, improvements_html,  Improvement)
        _save_section(patch_note, bug_fixes_html,     BugFix)
        _save_section(patch_note, special_notes_html, Remark)
        _save_section(patch_note, internal_notes_html, Internal)

        patch_note.translation_status = PatchNote.TRANSLATION_PENDING
        patch_note.save(update_fields=["translation_status", "updated_at"])
        start_translation(patch_note.id)

        return JsonResponse({'message': '패치노트가 등록되었습니다.', 'patch_note_id': patch_note.id})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 패치노트 데이터 조회 API (수정 모달용)
# ──────────────────────────────────────────────

@require_GET
@role_required('dev')
def get_patch_note_data(request, patch_note_id):
    try:
        note = PatchNote.objects.prefetch_related(
            'features', 'improvements', 'bugfixes', 'remarks', 'internals',
        ).get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    return JsonResponse({
        'id': note.id,
        'version': note.version,
        'release_date': str(note.release_date),
        'features_html':     _get_section_html(note.features),
        'improvements_html': _get_section_html(note.improvements),
        'bugfixes_html':     _get_section_html(note.bugfixes),
        'remarks_html':      _get_section_html(note.remarks),
        'internals_html':    _get_section_html(note.internals),
    })


# ──────────────────────────────────────────────
# 패치노트 수정 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_update(request):
    try:
        patch_note_id        = request.POST.get('patch_note_id', '').strip()
        version              = request.POST.get('version', '').strip()
        patch_date           = request.POST.get('patch_date', '').strip()

        new_features_html    = request.POST.get('new_features', '')
        improvements_html    = request.POST.get('improvements', '')
        bug_fixes_html       = request.POST.get('bug_fixes', '')
        special_notes_html   = request.POST.get('special_notes', '')
        internal_notes_html  = request.POST.get('internal_notes', '')

        if not patch_note_id:
            return JsonResponse({'error': '패치노트 ID가 누락되었습니다.'}, status=400)
        if not version:
            return JsonResponse({'error': '버전을 입력해주세요.'}, status=400)
        if not patch_date:
            return JsonResponse({'error': '배포 날짜를 입력해주세요.'}, status=400)

        try:
            note = PatchNote.objects.get(id=patch_note_id)
        except PatchNote.DoesNotExist:
            return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

        if PatchNote.objects.filter(product=note.product, version=version).exclude(id=note.id).exists():
            return JsonResponse({'error': f'버전 {version}은 이미 등록되어 있습니다.'}, status=400)

        note.version = version
        note.release_date = patch_date
        note.save()

        note.features.all().delete()
        note.improvements.all().delete()
        note.bugfixes.all().delete()
        note.remarks.all().delete()
        note.internals.all().delete()

        _save_section(note, new_features_html,  Feature)
        _save_section(note, improvements_html,  Improvement)
        _save_section(note, bug_fixes_html,     BugFix)
        _save_section(note, special_notes_html, Remark)
        _save_section(note, internal_notes_html, Internal)

        note.translation_status = PatchNote.TRANSLATION_PENDING
        note.save(update_fields=["translation_status", "updated_at"])
        start_translation(note.id)

        return JsonResponse({'message': '패치노트가 수정되었습니다.', 'patch_note_id': note.id})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 패치노트 삭제 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_delete(request):
    try:
        patch_note_id = request.POST.get('patch_note_id', '').strip()
        if not patch_note_id:
            return JsonResponse({'error': '패치노트 ID가 누락되었습니다.'}, status=400)

        try:
            note = PatchNote.objects.get(id=patch_note_id)
        except PatchNote.DoesNotExist:
            return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

        version = note.version
        note.delete()
        return JsonResponse({'message': f'버전 {version} 패치노트가 삭제되었습니다.'})

    except Exception as e:
        return JsonResponse({'error': f'서버 오류: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# 번역 상태 확인 API
# ──────────────────────────────────────────────

@require_POST
@role_required('dev')
def patch_note_publish(request):
    """패치노트 발행 — is_published=True 설정 및 즉시 구독자 알림"""
    patch_note_id = request.POST.get('patch_note_id', '').strip()
    if not patch_note_id:
        return JsonResponse({'error': '패치노트 ID가 누락되었습니다.'}, status=400)

    try:
        note = PatchNote.objects.select_related('product__solution').prefetch_related(
            'features', 'improvements', 'bugfixes', 'remarks'
        ).get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    if note.is_published:
        return JsonResponse({'error': '이미 발행된 패치노트입니다.'}, status=400)

    note.is_published = True
    note.save(update_fields=['is_published', 'updated_at'])

    # 즉시 처리: Notion 등록, 사내 Slack 알림 (Internal 항목 포함)
    _push_to_notion_safe(note, is_new=True)
    _send_internal_slack_notification(note)

    # 외부 발송 (고객사 Slack/Gmail) — SiteConfig 의 지연 시간만큼 미뤄서 Q2 task로 처리
    try:
        _schedule_external_send(note)
    except Exception as e:
        logger.exception(f'외부 발송 예약 실패 (id={note.id}): {e}')
        note.external_send_status = PatchNote.EXTERNAL_SEND_FAILED
        note.external_send_error = f'예약 실패: {e}'[:1000]
        note.save(update_fields=['external_send_status', 'external_send_error', 'updated_at'])

    msg = f'버전 {note.version} 이(가) 발행되었습니다.'
    if note.external_send_status == PatchNote.EXTERNAL_SEND_PENDING and note.external_send_scheduled_at:
        msg += f" 외부 발송 예정 시각: {timezone.localtime(note.external_send_scheduled_at):%Y-%m-%d %H:%M}"
    return JsonResponse({
        'message': msg,
        'external_send_status': note.external_send_status,
        'external_send_scheduled_at': (
            timezone.localtime(note.external_send_scheduled_at).isoformat()
            if note.external_send_scheduled_at else None
        ),
    })


@require_GET
@role_required('dev')
def translation_status(request, patch_note_id):
    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    return JsonResponse({
        'patch_note_id': note.id,
        'status': note.translation_status,
    })


# ──────────────────────────────────────────────
# 외부 발송 제어 (즉시 발송 / 취소)
# ──────────────────────────────────────────────

def _delete_q2_schedule(task_id: str):
    """Q2 Schedule 레코드를 삭제 (취소/즉시발송 시 중복 실행 방지)."""
    if not task_id:
        return
    try:
        from django_q.models import Schedule
        Schedule.objects.filter(id=task_id).delete()
    except Exception as e:
        logger.warning(f'Q2 Schedule 삭제 실패 (task_id={task_id}): {e}')


@require_POST
@role_required('manager')
def external_send_now(request, patch_note_id):
    """대기 중인 외부 발송을 즉시 실행"""
    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    if note.external_send_status != PatchNote.EXTERNAL_SEND_PENDING:
        return JsonResponse({
            'error': f'대기 중인 발송이 아닙니다. (현재 상태: {note.get_external_send_status_display()})'
        }, status=400)

    _delete_q2_schedule(note.external_send_task_id)

    try:
        from django_q.tasks import async_task
        task_id = async_task(
            'apps.patchnote.views.dispatch_external_notifications',
            note.id,
            task_name=f'patchnote-extsend-now-{note.id}',
        )
        note.external_send_task_id = task_id or ''
        note.external_send_scheduled_at = timezone.now()
        note.save(update_fields=[
            'external_send_task_id', 'external_send_scheduled_at', 'updated_at',
        ])
        return JsonResponse({'message': f'버전 {note.version} 외부 발송을 즉시 실행했습니다.'})
    except Exception as e:
        logger.exception(f'외부 즉시 발송 실패 (id={note.id})')
        return JsonResponse({'error': f'발송 실행 중 오류: {e}'}, status=500)


@require_POST
@role_required('manager')
def external_send_cancel(request, patch_note_id):
    """대기 중인 외부 발송을 취소"""
    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    if note.external_send_status != PatchNote.EXTERNAL_SEND_PENDING:
        return JsonResponse({
            'error': f'대기 중인 발송이 아닙니다. (현재 상태: {note.get_external_send_status_display()})'
        }, status=400)

    _delete_q2_schedule(note.external_send_task_id)

    note.external_send_status = PatchNote.EXTERNAL_SEND_CANCELLED
    note.external_send_task_id = ''
    note.save(update_fields=['external_send_status', 'external_send_task_id', 'updated_at'])

    return JsonResponse({'message': f'버전 {note.version} 외부 발송이 취소되었습니다.'})


# ──────────────────────────────────────────────
# 파일 업로드 / 다운로드 / 삭제
# ──────────────────────────────────────────────

def _format_file_size(size_bytes):
    """파일 크기를 사람이 읽기 쉬운 형태로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


@require_POST
@role_required('dev')
def patch_note_file_upload(request):
    """패치노트 파일 업로드 (release / debug)"""
    patch_note_id = request.POST.get('patch_note_id', '').strip()
    file_type = request.POST.get('file_type', '').strip()

    if not patch_note_id or not file_type:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)
    if file_type not in ('release', 'debug'):
        return JsonResponse({'error': '유효하지 않은 파일 유형입니다.'}, status=400)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': '파일이 첨부되지 않았습니다.'}, status=400)

    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    pf = PatchNoteFile.objects.create(
        patch_note=note,
        file_type=file_type,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        file_size=uploaded_file.size,
        uploaded_by=request.user,
    )

    # Nextcloud 이중 저장
    if upload_to_nextcloud(pf.file):
        share_url = create_share_link(pf.file)
        if share_url:
            pf.nextcloud_url = share_url
            pf.save(update_fields=['nextcloud_url'])

    return JsonResponse({
        'message': '파일이 업로드되었습니다.',
        'file': {
            'id': pf.id,
            'file_type': pf.file_type,
            'original_filename': pf.original_filename,
            'file_size': pf.file_size,
            'file_size_display': _format_file_size(pf.file_size),
            'created_at': pf.created_at.strftime('%Y-%m-%d %H:%M'),
            'nextcloud_url': pf.nextcloud_url or '',
        },
    })


@require_GET
def patch_note_file_download(request, file_id):
    """파일 다운로드 — debug 파일은 admin/dev만 허용"""
    if not request.user.is_authenticated:
        raise PermissionDenied

    pf = get_object_or_404(PatchNoteFile, id=file_id)

    if pf.file_type == 'debug':
        role = get_user_role(request.user)
        if role not in ('admin', 'dev'):
            raise PermissionDenied

    if not pf.file:
        raise Http404

    return FileResponse(pf.file.open('rb'), as_attachment=True, filename=pf.original_filename)


@require_POST
@role_required('dev')
def patch_note_file_delete(request):
    """파일 삭제"""
    file_id = request.POST.get('file_id', '').strip()
    if not file_id:
        return JsonResponse({'error': '파일 ID가 누락되었습니다.'}, status=400)

    try:
        pf = PatchNoteFile.objects.get(id=file_id)
    except PatchNoteFile.DoesNotExist:
        return JsonResponse({'error': '파일을 찾을 수 없습니다.'}, status=404)

    # Nextcloud에서도 삭제
    delete_from_nextcloud(pf.file)

    pf.file.delete(save=False)
    pf.delete()

    return JsonResponse({'message': '파일이 삭제되었습니다.'})


@require_GET
def patch_note_files_list(request, patch_note_id):
    """패치노트의 파일 목록 JSON 반환"""
    if not request.user.is_authenticated:
        raise PermissionDenied

    try:
        note = PatchNote.objects.get(id=patch_note_id)
    except PatchNote.DoesNotExist:
        return JsonResponse({'error': '패치노트를 찾을 수 없습니다.'}, status=404)

    role = get_user_role(request.user)
    files = note.files.all()

    result = []
    for pf in files:
        if pf.file_type == 'debug' and role not in ('admin', 'dev'):
            continue
        result.append({
            'id': pf.id,
            'file_type': pf.file_type,
            'file_type_display': pf.get_file_type_display(),
            'original_filename': pf.original_filename,
            'file_size': pf.file_size,
            'file_size_display': _format_file_size(pf.file_size),
            'created_at': pf.created_at.strftime('%Y-%m-%d %H:%M'),
            'nextcloud_url': pf.nextcloud_url or '',
        })

    return JsonResponse({'files': result})

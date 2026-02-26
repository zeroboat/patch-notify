"""
slack_bolt App 인스턴스 + 이벤트 핸들러 정의
- app_home_opened : Home Tab 렌더링
- open_subscription_modal : 설정 모달 열기
- save_subscription (view_submission) : 구독 저장
"""
import django
from django.conf import settings
from slack_bolt import App

from .installation_store import DjangoInstallationStore

bolt_app = App(
    signing_secret=settings.SLACK_SIGNING_SECRET,
    installation_store=DjangoInstallationStore(),
)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _get_approved_workspace(team_id):
    from .models import SlackWorkspace
    return SlackWorkspace.objects.filter(
        team_id=team_id,
        status=SlackWorkspace.STATUS_APPROVED,
    ).select_related('customer').first()


def _pending_view():
    return {
        "type": "home",
        "blocks": [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "⏳ *승인 대기 중*\n\n"
                    "관리자가 워크스페이스를 확인 후 승인하면 이용할 수 있습니다.\n"
                    "문의: 담당자에게 연락해 주세요."
                ),
            },
        }],
    }


# ── app_home_opened ────────────────────────────────────────────────────────────

@bolt_app.event("app_home_opened")
def handle_app_home_opened(event, client, body):
    from .home_tab import build_home_tab

    user_id = event['user']
    team_id = body.get('team_id') or body.get('team', {}).get('id', '')

    workspace = _get_approved_workspace(team_id)

    if not workspace or not workspace.customer:
        client.views_publish(user_id=user_id, view=_pending_view())
        return

    blocks = build_home_tab(workspace.customer)
    client.views_publish(
        user_id=user_id,
        view={"type": "home", "blocks": blocks},
    )


# ── 설정 변경 버튼 → 모달 열기 ────────────────────────────────────────────────

@bolt_app.action("open_subscription_modal")
def handle_open_subscription_modal(ack, body, client):
    from apps.product.models import Solution
    from .home_tab import build_subscription_modal

    ack()

    team_id = body['team']['id']
    solution_id = body['actions'][0]['value']

    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer:
        return

    try:
        solution = Solution.objects.get(id=solution_id)
    except Solution.DoesNotExist:
        return

    modal = build_subscription_modal(workspace.customer, solution)
    client.views_open(trigger_id=body['trigger_id'], view=modal)


# ── 모달 제출 → 구독 저장 ──────────────────────────────────────────────────────

@bolt_app.view("save_subscription")
def handle_save_subscription(ack, body, view, client):
    from apps.product.models import Solution
    from apps.subscriber.models import Subscription
    from .home_tab import build_home_tab

    ack()

    team_id = body['team']['id']
    user_id = body['user']['id']

    # private_metadata = "customer_id:solution_id"
    customer_id, solution_id = view['private_metadata'].split(':')

    workspace = _get_approved_workspace(team_id)
    if not workspace or str(workspace.customer_id) != customer_id:
        return

    try:
        solution = Solution.objects.get(id=solution_id)
    except Solution.DoesNotExist:
        return

    customer = workspace.customer
    values = view['state']['values']

    # ── Gmail ──────────────────────────────────────────────────────────────────
    email_enabled = bool(
        values.get('email_toggle', {})
        .get('email_enabled', {})
        .get('selected_options', [])
    )
    email_freq = (
        values.get('email_frequency', {})
        .get('email_freq_select', {})
        .get('selected_option', {})
        .get('value', 'weekly')
    )
    email_max = int(
        values.get('email_max_items', {})
        .get('email_max_select', {})
        .get('selected_option', {})
        .get('value', '5')
    )

    if email_enabled:
        Subscription.objects.update_or_create(
            customer=customer, solution=solution, channel='email',
            defaults={'is_active': True, 'frequency': email_freq, 'max_items': email_max},
        )
    else:
        Subscription.objects.filter(
            customer=customer, solution=solution, channel='email'
        ).update(is_active=False)

    # ── Slack ──────────────────────────────────────────────────────────────────
    slack_enabled = bool(
        values.get('slack_toggle', {})
        .get('slack_enabled', {})
        .get('selected_options', [])
    )
    slack_channel = (
        values.get('slack_channel_input', {})
        .get('slack_channel_value', {})
        .get('value', '') or ''
    )
    slack_freq = (
        values.get('slack_frequency', {})
        .get('slack_freq_select', {})
        .get('selected_option', {})
        .get('value', 'weekly')
    )
    slack_max = int(
        values.get('slack_max_items', {})
        .get('slack_max_select', {})
        .get('selected_option', {})
        .get('value', '5')
    )

    if slack_enabled:
        Subscription.objects.update_or_create(
            customer=customer, solution=solution, channel='slack',
            defaults={
                'is_active': True,
                'slack_channel': slack_channel,
                'frequency': slack_freq,
                'max_items': slack_max,
            },
        )
    else:
        Subscription.objects.filter(
            customer=customer, solution=solution, channel='slack'
        ).update(is_active=False)

    # Home Tab 새로고침
    blocks = build_home_tab(customer)
    client.views_publish(
        user_id=user_id,
        view={"type": "home", "blocks": blocks},
    )

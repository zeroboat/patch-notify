"""Slack Home Tab & Modal Block Kit 빌더"""

from apps.subscriber.models import Subscription

_FREQ_OPTIONS = [
    {"text": {"type": "plain_text", "text": "매주"}, "value": "weekly"},
    {"text": {"type": "plain_text", "text": "매월"}, "value": "monthly"},
    {"text": {"type": "plain_text", "text": "분기"}, "value": "quarterly"},
]

_MAX_ITEMS_OPTIONS = [
    {"text": {"type": "plain_text", "text": f"{n}개"}, "value": str(n)}
    for n in [1, 2, 3, 5, 7, 10]
]


def _freq_initial(value):
    return next((o for o in _FREQ_OPTIONS if o["value"] == value), _FREQ_OPTIONS[0])


def _max_initial(value):
    return next((o for o in _MAX_ITEMS_OPTIONS if str(o["value"]) == str(value)), _MAX_ITEMS_OPTIONS[3])


def build_home_tab(customer):
    """고객사 구독 현황 Home Tab 블록 반환"""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 Patch Notify 구독 관리"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*고객사:* {customer.name}"},
        },
        {"type": "divider"},
    ]

    solutions = customer.solutions.order_by('name')

    if not solutions.exists():
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "구독 가능한 솔루션이 없습니다.\n담당자에게 문의해 주세요."},
        })
        return blocks

    for solution in solutions:
        email_sub = Subscription.objects.filter(
            customer=customer, solution=solution, channel='email'
        ).first()
        slack_sub = Subscription.objects.filter(
            customer=customer, solution=solution, channel='slack'
        ).first()

        email_on = email_sub and email_sub.is_active
        slack_on = slack_sub and slack_sub.is_active

        email_text = "✅ 활성화" if email_on else "❌ 비활성화"
        slack_text = f"✅ {slack_sub.slack_channel or '활성화'}" if slack_on else "❌ 비활성화"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{solution.name}*\n"
                    f"📧 Gmail: {email_text}   💬 Slack: {slack_text}"
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "설정 변경"},
                "action_id": "open_subscription_modal",
                "value": str(solution.id),
            },
        })

    return blocks


def build_subscription_modal(customer, solution):
    """구독 설정 모달 블록 반환"""
    email_sub = Subscription.objects.filter(
        customer=customer, solution=solution, channel='email'
    ).first()
    slack_sub = Subscription.objects.filter(
        customer=customer, solution=solution, channel='slack'
    ).first()

    email_active = bool(email_sub and email_sub.is_active)
    slack_active = bool(slack_sub and slack_sub.is_active)
    email_freq = email_sub.frequency if email_sub else 'weekly'
    email_max = str(email_sub.max_items) if email_sub else '5'
    slack_freq = slack_sub.frequency if slack_sub else 'weekly'
    slack_max = str(slack_sub.max_items) if slack_sub else '5'
    slack_channel = (slack_sub.slack_channel or '') if slack_sub else ''

    checkbox_option = [{"text": {"type": "plain_text", "text": "활성화"}, "value": "true"}]

    blocks = [
        # ── Gmail ──────────────────────────────────────────────
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📧 Gmail 알림*"},
        },
        {
            "type": "actions",
            "block_id": "email_toggle",
            "elements": [{
                "type": "checkboxes",
                "action_id": "email_enabled",
                "options": checkbox_option,
                "initial_options": checkbox_option if email_active else [],
            }],
        },
        {
            "type": "input",
            "block_id": "email_frequency",
            "label": {"type": "plain_text", "text": "전달 주기"},
            "element": {
                "type": "static_select",
                "action_id": "email_freq_select",
                "options": _FREQ_OPTIONS,
                "initial_option": _freq_initial(email_freq),
            },
            "optional": True,
        },
        {
            "type": "input",
            "block_id": "email_max_items",
            "label": {"type": "plain_text", "text": "최대 건수"},
            "element": {
                "type": "static_select",
                "action_id": "email_max_select",
                "options": _MAX_ITEMS_OPTIONS,
                "initial_option": _max_initial(email_max),
            },
            "optional": True,
        },
        {"type": "divider"},
        # ── Slack ──────────────────────────────────────────────
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*💬 Slack 알림*"},
        },
        {
            "type": "actions",
            "block_id": "slack_toggle",
            "elements": [{
                "type": "checkboxes",
                "action_id": "slack_enabled",
                "options": checkbox_option,
                "initial_options": checkbox_option if slack_active else [],
            }],
        },
        {
            "type": "input",
            "block_id": "slack_channel_input",
            "label": {"type": "plain_text", "text": "채널명 (예: #patch-notes)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "slack_channel_value",
                "initial_value": slack_channel,
                "placeholder": {"type": "plain_text", "text": "#patch-notes"},
            },
            "optional": True,
        },
        {
            "type": "input",
            "block_id": "slack_frequency",
            "label": {"type": "plain_text", "text": "전달 주기"},
            "element": {
                "type": "static_select",
                "action_id": "slack_freq_select",
                "options": _FREQ_OPTIONS,
                "initial_option": _freq_initial(slack_freq),
            },
            "optional": True,
        },
        {
            "type": "input",
            "block_id": "slack_max_items",
            "label": {"type": "plain_text", "text": "최대 건수"},
            "element": {
                "type": "static_select",
                "action_id": "slack_max_select",
                "options": _MAX_ITEMS_OPTIONS,
                "initial_option": _max_initial(slack_max),
            },
            "optional": True,
        },
    ]

    return {
        "type": "modal",
        "callback_id": "save_subscription",
        "title": {"type": "plain_text", "text": f"{solution.name[:24]} 구독 설정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "private_metadata": f"{customer.id}:{solution.id}",
        "blocks": blocks,
    }

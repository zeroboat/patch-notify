"""
slack_bolt App 인스턴스 + 이벤트 핸들러
FastAPI 어댑터를 통해 /slack/events/ 에서 수신
"""
import os
from datetime import datetime, timezone
from sqlalchemy import select, and_
from slack_bolt import App
from slack_sdk.oauth.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation

from database import SessionLocal
from models import slack_workspace, subscription, solution as sol_table
from home_tab import build_home_tab, build_subscription_modal, get_customer_solutions


# ── Installation Store ─────────────────────────────────────────────────────────

class SAInstallationStore(InstallationStore):
    """SQLAlchemy 기반 Installation Store"""

    def save(self, installation: Installation, **kwargs):
        db = SessionLocal()
        try:
            existing = db.execute(
                select(slack_workspace).where(slack_workspace.c.team_id == installation.team_id)
            ).fetchone()
            if existing:
                db.execute(
                    slack_workspace.update()
                    .where(slack_workspace.c.team_id == installation.team_id)
                    .values(team_name=installation.team_name or '', bot_token=installation.bot_token, updated_at=datetime.now(timezone.utc))
                )
            else:
                now = datetime.now(timezone.utc)
                db.execute(slack_workspace.insert().values(
                    team_id=installation.team_id,
                    team_name=installation.team_name or '',
                    bot_token=installation.bot_token,
                    status='pending',
                    created_at=now,
                    updated_at=now,
                ))
            db.commit()
        finally:
            db.close()

    def find_bot(self, *, enterprise_id=None, team_id=None, **kwargs):
        db = SessionLocal()
        try:
            row = db.execute(
                select(slack_workspace).where(slack_workspace.c.team_id == team_id)
            ).fetchone()
            if not row:
                return None
            return Bot(bot_token=row.bot_token, team_id=row.team_id, team_name=row.team_name)
        finally:
            db.close()

    def find_installation(self, *, enterprise_id=None, team_id=None, **kwargs):
        db = SessionLocal()
        try:
            row = db.execute(
                select(slack_workspace).where(slack_workspace.c.team_id == team_id)
            ).fetchone()
            if not row:
                return None
            return Installation(bot_token=row.bot_token, team_id=row.team_id, team_name=row.team_name, user_id="")
        finally:
            db.close()


# ── Bolt App ───────────────────────────────────────────────────────────────────

bolt_app = App(
    signing_secret=os.environ['SLACK_SIGNING_SECRET'],
    installation_store=SAInstallationStore(),
)


def _get_approved_workspace(team_id: str):
    db = SessionLocal()
    try:
        return db.execute(
            select(slack_workspace).where(
                and_(
                    slack_workspace.c.team_id == team_id,
                    slack_workspace.c.status == 'approved',
                )
            )
        ).fetchone()
    finally:
        db.close()


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
    # print("home tab test") // 디버깅용 로그
    user_id = event['user']
    team_id = body.get('team_id') or body.get('team', {}).get('id', '')

    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer_id:
        client.views_publish(user_id=user_id, view=_pending_view())
        return

    db = SessionLocal()
    try:
        from models import customer as customer_table
        customer_row = db.execute(
            select(customer_table).where(customer_table.c.id == workspace.customer_id)
        ).fetchone()
        customer_name = customer_row.name if customer_row else workspace.team_name
        blocks = build_home_tab(db, workspace.customer_id, customer_name)
    finally:
        db.close()

    client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})


# ── 설정 변경 버튼 → 모달 열기 ────────────────────────────────────────────────

@bolt_app.action("open_subscription_modal")
def handle_open_subscription_modal(ack, body, client):
    ack()

    team_id = body['team']['id']
    solution_id = int(body['actions'][0]['value'])

    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer_id:
        return

    db = SessionLocal()
    try:
        sol_row = db.execute(
            select(sol_table).where(sol_table.c.id == solution_id)
        ).fetchone()
        if not sol_row:
            return
        modal = build_subscription_modal(db, workspace.customer_id, solution_id, sol_row.name)
    finally:
        db.close()

    client.views_open(trigger_id=body['trigger_id'], view=modal)


# ── 모달 제출 → 구독 저장 ──────────────────────────────────────────────────────

@bolt_app.view("save_subscription")
def handle_save_subscription(ack, body, view, client):
    ack()

    team_id = body['team']['id']
    user_id = body['user']['id']
    customer_id, solution_id = (int(x) for x in view['private_metadata'].split(':'))

    workspace = _get_approved_workspace(team_id)
    if not workspace or workspace.customer_id != customer_id:
        return

    values = view['state']['values']

    # ── Gmail ──────────────────────────────────────────────────────────────────
    email_enabled = bool(
        values.get('email_toggle', {}).get('email_enabled', {}).get('selected_options', [])
    )
    email_freq = (
        values.get('email_frequency', {}).get('email_freq_select', {})
        .get('selected_option', {}).get('value', 'weekly')
    )
    email_max = int(
        values.get('email_max_items', {}).get('email_max_select', {})
        .get('selected_option', {}).get('value', '5')
    )

    # ── Slack ──────────────────────────────────────────────────────────────────
    slack_enabled = bool(
        values.get('slack_toggle', {}).get('slack_enabled', {}).get('selected_options', [])
    )
    slack_channel_val = (
        values.get('slack_channel_input', {}).get('slack_channel_value', {}).get('value', '') or ''
    )
    slack_freq = (
        values.get('slack_frequency', {}).get('slack_freq_select', {})
        .get('selected_option', {}).get('value', 'weekly')
    )
    slack_max = int(
        values.get('slack_max_items', {}).get('slack_max_select', {})
        .get('selected_option', {}).get('value', '5')
    )

    db = SessionLocal()
    try:
        _upsert_subscription(db, customer_id, solution_id, 'email', email_enabled, email_freq, email_max, None)
        _upsert_subscription(db, customer_id, solution_id, 'slack', slack_enabled, slack_freq, slack_max, slack_channel_val)
        db.commit()
        from models import customer as customer_table
        customer_row = db.execute(
            select(customer_table).where(customer_table.c.id == customer_id)
        ).fetchone()
        customer_name = customer_row.name if customer_row else workspace.team_name
        blocks = build_home_tab(db, customer_id, customer_name)
    finally:
        db.close()

    client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})


def _upsert_subscription(db, customer_id, solution_id, channel, enabled, freq, max_items, slack_ch):
    existing = db.execute(
        select(subscription).where(
            and_(
                subscription.c.customer_id == customer_id,
                subscription.c.solution_id == solution_id,
                subscription.c.channel == channel,
            )
        )
    ).fetchone()

    if existing:
        update_vals = {'is_active': enabled, 'frequency': freq, 'max_items': max_items}
        if slack_ch is not None:
            update_vals['slack_channel'] = slack_ch
        db.execute(
            subscription.update()
            .where(subscription.c.id == existing.id)
            .values(**update_vals)
        )
    elif enabled:
        insert_vals = {
            'customer_id': customer_id,
            'solution_id': solution_id,
            'channel': channel,
            'is_active': True,
            'frequency': freq,
            'max_items': max_items,
        }
        if slack_ch is not None:
            insert_vals['slack_channel'] = slack_ch
        db.execute(subscription.insert().values(**insert_vals))

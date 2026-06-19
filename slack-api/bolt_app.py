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
from models import (
    slack_workspace, subscription, product as product_table,
    utility as utility_table, utility_subscription as util_sub_table,
)
from home_tab import (
    build_home_tab, build_subscription_modal, build_channel_settings_modal,
    build_patchnote_blocks, build_utility_patchnote_blocks,
    build_patchnote_select_modal, build_email_modal,
    get_customer_solutions,
)


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
                    is_internal=False,
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
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📋 Patch Notify 구독 관리"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*⏳ 승인 대기 중*\n\n관리자가 워크스페이스를 확인한 후 승인하면 이용할 수 있습니다.",
                },
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "문의가 있으시면 담당자에게 연락해 주세요."}],
            },
        ],
    }


# ── app_home_opened ────────────────────────────────────────────────────────────

@bolt_app.event("app_home_opened")
def handle_app_home_opened(event, client, body):
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


# ── URL 버튼 ack (open_subscribe_web, open_patchnote_web) ─────────────────────

@bolt_app.action("open_subscribe_web")
def handle_open_subscribe_web(ack, body):
    ack()


@bolt_app.action("open_patchnote_web")
def handle_open_patchnote_web(ack, body):
    ack()


# ── Slack 채널 설정 버튼 → 통합 채널 설정 모달 ──────────────────────────────

@bolt_app.action("open_channel_settings_modal")
def handle_open_channel_settings_modal(ack, body, client):
    ack()

    team_id = body['team']['id']
    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer_id:
        return

    db = SessionLocal()
    try:
        modal = build_channel_settings_modal(db, workspace.customer_id)
    finally:
        db.close()

    client.views_open(trigger_id=body['trigger_id'], view=modal)


# ── 채널 설정 모달 제출 → 전체 솔루션 Slack 구독 저장 ────────────────────────

@bolt_app.view("save_channel_settings")
def handle_save_channel_settings(ack, body, view, client):
    ack()

    team_id = body['team']['id']
    user_id = body['user']['id']
    customer_id = int(view['private_metadata'])

    workspace = _get_approved_workspace(team_id)
    if not workspace or workspace.customer_id != customer_id:
        return

    values = view['state']['values']

    db = SessionLocal()
    try:
        solutions = get_customer_solutions(db, customer_id)

        for sol in solutions:
            block_ch = f"slack_channel_{sol.id}"
            block_prod = f"slack_products_{sol.id}"

            slack_ch = (
                values.get(block_ch, {}).get('slack_channel_value', {})
                .get('selected_conversation') or ''
            )
            slack_selected = {
                int(o['value'])
                for o in values.get(block_prod, {}).get('slack_products_select', {})
                .get('selected_options', [])
            }

            products = db.execute(
                select(product_table).where(product_table.c.solution_id == sol.id)
            ).fetchall()

            for p in products:
                _upsert_subscription(db, customer_id, p.id, 'slack', p.id in slack_selected, slack_ch)

        # 유틸리티 구독 저장
        import re
        utilities = db.execute(select(utility_table)).fetchall()
        util_id_set = {u.id for u in utilities}
        for block_id, block_val in values.items():
            m = re.match(r'^utility_channel_(\d+)$', block_id)
            if not m:
                continue
            util_id = int(m.group(1))
            if util_id not in util_id_set:
                continue
            slack_ch = block_val.get('utility_channel_value', {}).get('selected_conversation') or ''
            active_block = f"utility_active_{util_id}"
            is_active = bool(
                values.get(active_block, {}).get('utility_active_select', {}).get('selected_options')
            )
            _upsert_utility_subscription(db, customer_id, util_id, is_active, slack_ch)

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


def _upsert_utility_subscription(db, customer_id, utility_id, is_active, slack_ch):
    existing = db.execute(
        select(util_sub_table).where(
            and_(
                util_sub_table.c.customer_id == customer_id,
                util_sub_table.c.utility_id == utility_id,
            )
        )
    ).fetchone()
    if existing:
        db.execute(
            util_sub_table.update()
            .where(util_sub_table.c.id == existing.id)
            .values(is_active=is_active, slack_channel=slack_ch or None)
        )
    elif is_active:
        now = datetime.now(timezone.utc)
        db.execute(util_sub_table.insert().values(
            customer_id=customer_id,
            utility_id=utility_id,
            is_active=True,
            slack_channel=slack_ch or None,
            created_at=now,
        ))


def _upsert_subscription(db, customer_id, product_id, channel, enabled, slack_ch):
    existing = db.execute(
        select(subscription).where(
            and_(
                subscription.c.customer_id == customer_id,
                subscription.c.product_id == product_id,
                subscription.c.channel == channel,
            )
        )
    ).fetchone()

    if existing:
        update_vals = {
            'is_active': enabled,
            'updated_at': datetime.now(timezone.utc),
        }
        if slack_ch is not None:
            update_vals['slack_channel'] = slack_ch
        db.execute(
            subscription.update()
            .where(subscription.c.id == existing.id)
            .values(**update_vals)
        )
    elif enabled:
        now = datetime.now(timezone.utc)
        insert_vals = {
            'customer_id': customer_id,
            'product_id': product_id,
            'channel': channel,
            'is_active': True,
            'created_at': now,
            'updated_at': now,
        }
        if slack_ch is not None:
            insert_vals['slack_channel'] = slack_ch
        db.execute(subscription.insert().values(**insert_vals))


# ── 수신 이메일 확인 버튼 → 이메일 목록 모달 ─────────────────────────────────

@bolt_app.action("view_emails")
def handle_view_emails(ack, body, client):
    ack()

    team_id = body['team']['id']
    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer_id:
        return

    db = SessionLocal()
    try:
        modal = build_email_modal(db, workspace.customer_id)
    finally:
        db.close()

    client.views_open(trigger_id=body['trigger_id'], view=modal)


# ── 최근 패치노트 버튼 → 솔루션/제품 통합 선택 모달 ─────────────────────────────

@bolt_app.action("view_all_patchnotes")
def handle_view_all_patchnotes(ack, body, client):
    ack()

    team_id = body['team']['id']
    workspace = _get_approved_workspace(team_id)
    if not workspace or not workspace.customer_id:
        return

    db = SessionLocal()
    try:
        modal = build_patchnote_select_modal(db, workspace.customer_id)
    finally:
        db.close()

    client.views_open(trigger_id=body['trigger_id'], view=modal)


# ── 패치노트 제품 선택 모달 제출 → DM으로 패치노트 전송 ──────────────────────────

@bolt_app.view("select_patchnote_product")
def handle_select_patchnote_product(ack, body, view, client):
    ack()

    user_id = body['user']['id']
    selected_value = view['state']['values']['patchnote_product']['product_id']['selected_option']['value']

    db = SessionLocal()
    try:
        if selected_value.startswith('u:'):
            _, util_id_str, utility_name = selected_value.split(':', 2)
            blocks = build_utility_patchnote_blocks(db, int(util_id_str), utility_name)
            label = utility_name
        else:
            product_id_str, solution_name = selected_value.split(':', 1)
            blocks = build_patchnote_blocks(db, int(product_id_str), solution_name)
            label = solution_name
    finally:
        db.close()

    try:
        client.chat_postMessage(channel=user_id, blocks=blocks, text=f"{label} 최근 패치노트")
    except Exception as e:
        client.chat_postMessage(
            channel=user_id,
            text=f"패치노트 전송 중 오류가 발생했습니다: {e}",
        )

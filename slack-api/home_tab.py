"""Slack Home Tab & Modal Block Kit 빌더"""
import re
from sqlalchemy.orm import Session
from sqlalchemy import select, and_


def html_to_mrkdwn(html: str) -> str:
    """HTML → Slack mrkdwn 변환 (<ul> 깊이 기반 들여쓰기)"""
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
        else:
            token = token.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            result.append(token)

    text = re.sub(r'\n{3,}', '\n\n', ''.join(result))
    return text.lstrip('\n').rstrip()


from models import (
    solution as sol_table, subscription as sub_table,
    customer_solutions as cs_table, customer_email as email_table,
    product as product_table, patchnote as patchnote_table,
    patchnote_feature, patchnote_improvement, patchnote_bugfix, patchnote_remark,
)

_MAX_ITEMS_OPTIONS = [
    {"text": {"type": "plain_text", "text": f"{n}개"}, "value": str(n)}
    for n in [1, 2, 3, 5, 7, 10]
]

_PLATFORM_LABEL = {
    'AOS': 'Android', 'IOS': 'iOS', 'SERVER': 'Server',
    'MACOS': 'macOS', 'WEB': 'Web', 'FLUTTER': 'Flutter',
}
_CATEGORY_LABEL = {
    'LIB': 'Library', 'PLG': 'Plugin', 'BND': 'Backend',
    'FND': 'Frontend', 'MOD': 'Module',
}


def _max_initial(value):
    return next((o for o in _MAX_ITEMS_OPTIONS if str(o["value"]) == str(value)), _MAX_ITEMS_OPTIONS[3])


def _get_subscription(db: Session, customer_id: int, product_id: int, channel: str):
    return db.execute(
        select(sub_table).where(
            and_(
                sub_table.c.customer_id == customer_id,
                sub_table.c.product_id == product_id,
                sub_table.c.channel == channel,
            )
        )
    ).fetchone()


def get_customer_solutions(db: Session, customer_id: int):
    return db.execute(
        select(sol_table).join(
            cs_table, cs_table.c.solution_id == sol_table.c.id
        ).where(cs_table.c.customer_id == customer_id).order_by(sol_table.c.name)
    ).fetchall()


def build_home_tab(db: Session, customer_id: int, customer_name: str) -> list:
    emails = db.execute(
        select(email_table).where(email_table.c.customer_id == customer_id)
    ).fetchall()

    email_lines = '\n'.join(
        f"• {r.email}" + (f" ({r.name})" if r.name else "")
        for r in emails
    )
    customer_text = f"*고객사:* {customer_name}"
    if email_lines:
        customer_text += f"\n*수신 이메일:*\n{email_lines}"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📋 Patch Notify 구독 관리"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": customer_text}},
        {"type": "divider"},
    ]

    solutions = get_customer_solutions(db, customer_id)

    if not solutions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "구독 가능한 솔루션이 없습니다.\n담당자에게 문의해 주세요."},
        })
        return blocks

    for sol in solutions:
        products = db.execute(
            select(product_table).where(product_table.c.solution_id == sol.id)
        ).fetchall()

        email_active = sum(
            1 for p in products
            if (s := _get_subscription(db, customer_id, p.id, 'email')) and s.is_active
        )
        slack_active = sum(
            1 for p in products
            if (s := _get_subscription(db, customer_id, p.id, 'slack')) and s.is_active
        )
        total = len(products)

        if total == 0:
            email_text = "❌ 제품 없음"
            slack_text = "❌ 제품 없음"
        else:
            email_text = f"✅ {email_active}/{total}개 활성" if email_active else "❌ 비활성화"
            slack_text = f"✅ {slack_active}/{total}개 활성" if slack_active else "❌ 비활성화"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{sol.name}*\n"
                    f"📧 Gmail: {email_text}   💬 Slack: {slack_text}"
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "설정 변경"},
                "action_id": "open_subscription_modal",
                "value": str(sol.id),
            },
        })
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "📄 최근 패치노트 보기"},
                "action_id": "view_recent_patchnotes",
                "value": str(sol.id),
            }],
        })

    return blocks


def build_subscription_modal(db: Session, customer_id: int, solution_id: int, solution_name: str) -> dict:
    """솔루션 단위 구독 설정 모달 — 제품 선택 + 공통 설정"""
    products = db.execute(
        select(product_table).where(product_table.c.solution_id == solution_id)
    ).fetchall()

    if not products:
        return _simple_modal(f"{solution_name} 구독 설정", "등록된 제품이 없습니다.")

    product_options = [
        {
            "text": {"type": "plain_text", "text": f"{_PLATFORM_LABEL.get(p.platform, p.platform)} {_CATEGORY_LABEL.get(p.category, p.category)}"},
            "value": str(p.id),
        }
        for p in products
    ]

    # 현재 활성화된 제품 및 공통 설정 수집
    email_active_opts, slack_active_opts = [], []
    email_max, slack_max, slack_channel = '5', '5', ''

    for p, opt in zip(products, product_options):
        email_sub = _get_subscription(db, customer_id, p.id, 'email')
        slack_sub = _get_subscription(db, customer_id, p.id, 'slack')
        if email_sub and email_sub.is_active:
            email_active_opts.append(opt)
            email_max = str(email_sub.max_items)
        if slack_sub and slack_sub.is_active:
            slack_active_opts.append(opt)
            slack_max = str(slack_sub.max_items)
            if slack_sub.slack_channel:
                slack_channel = slack_sub.slack_channel

    # 제품 체크박스 element 빌더
    def _product_checkboxes(action_id, initial):
        el = {"type": "checkboxes", "action_id": action_id, "options": product_options}
        if initial:
            el["initial_options"] = initial
        return el

    channel_element = {
        "type": "conversations_select",
        "action_id": "slack_channel_value",
        "placeholder": {"type": "plain_text", "text": "채널 선택"},
        "filter": {"include": ["public"], "exclude_bot_users": True},
    }
    if slack_channel:
        channel_element["initial_conversation"] = slack_channel

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*📧 Gmail 알림*"}},
        {
            "type": "input",
            "block_id": "email_products",
            "label": {"type": "plain_text", "text": "전달 받을 제품"},
            "element": _product_checkboxes("email_products_select", email_active_opts),
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
        {"type": "section", "text": {"type": "mrkdwn", "text": "*💬 Slack 알림*"}},
        {
            "type": "input",
            "block_id": "slack_products",
            "label": {"type": "plain_text", "text": "전달 받을 제품"},
            "element": _product_checkboxes("slack_products_select", slack_active_opts),
            "optional": True,
        },
        {
            "type": "input",
            "block_id": "slack_channel_input",
            "label": {"type": "plain_text", "text": "알림 채널"},
            "element": channel_element,
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
        "title": {"type": "plain_text", "text": f"{solution_name} 구독 설정"[:24]},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "private_metadata": f"{customer_id}:{solution_id}",
        "blocks": blocks,
    }


def build_product_select_modal(db: Session, solution_id: int, solution_name: str) -> dict:
    """패치노트 조회를 위한 제품 선택 모달"""
    products = db.execute(
        select(product_table).where(product_table.c.solution_id == solution_id)
    ).fetchall()

    if not products:
        return _simple_modal(solution_name, "등록된 제품이 없습니다.")

    options = [
        {
            "text": {"type": "plain_text", "text": f"{_PLATFORM_LABEL.get(p.platform, p.platform)} {_CATEGORY_LABEL.get(p.category, p.category)}"},
            "value": str(p.id),
        }
        for p in products
    ]

    return {
        "type": "modal",
        "callback_id": "send_patchnote_dm",
        "title": {"type": "plain_text", "text": "제품 선택"},
        "submit": {"type": "plain_text", "text": "패치노트 보기"},
        "close": {"type": "plain_text", "text": "취소"},
        "private_metadata": f"{solution_id}:{solution_name}",
        "blocks": [{
            "type": "input",
            "block_id": "product_select",
            "label": {"type": "plain_text", "text": f"{solution_name} 하위 제품"},
            "element": {
                "type": "static_select",
                "action_id": "product_id",
                "options": options,
                "placeholder": {"type": "plain_text", "text": "제품 선택"},
            },
        }],
    }


def _fetch_items(db, table, note_id):
    return db.execute(
        select(table).where(
            and_(table.c.patch_note_id == note_id, table.c.parent_id == None)
        ).order_by(table.c.order)
    ).fetchall()


def _items_text(rows) -> str:
    if not rows:
        return "  - N/A"
    return '\n'.join(html_to_mrkdwn(r.content) for r in rows)


def build_patchnote_blocks(db: Session, product_id: int, solution_name: str) -> list:
    """제품의 최근 3개 패치노트를 메시지 블록으로 반환"""
    product_row = db.execute(
        select(product_table).where(product_table.c.id == product_id)
    ).fetchone()

    product_label = ""
    if product_row:
        platform = _PLATFORM_LABEL.get(product_row.platform, product_row.platform)
        category = _CATEGORY_LABEL.get(product_row.category, product_row.category)
        product_label = f" {platform} {category}"

    notes = db.execute(
        select(patchnote_table)
        .where(
            and_(
                patchnote_table.c.product_id == product_id,
                patchnote_table.c.is_published == True,
            )
        )
        .order_by(patchnote_table.c.release_date.desc())
        .limit(3)
    ).fetchall()

    if not notes:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "등록된 패치노트가 없습니다."}}]

    title = f"{solution_name}{product_label} 최근 패치노트"
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}}]

    for note in notes:
        features = _fetch_items(db, patchnote_feature, note.id)
        improves = _fetch_items(db, patchnote_improvement, note.id)
        bugfixes = _fetch_items(db, patchnote_bugfix, note.id)
        remarks  = _fetch_items(db, patchnote_remark, note.id)

        body = (
            f"[Patch Note]\n"
            f"기능 추가\n{_items_text(features)}\n\n"
            f"기능 개선\n{_items_text(improves)}\n\n"
            f"버그 수정\n{_items_text(bugfixes)}"
        )
        if remarks:
            body += f"\n\n[Remarks]\n{_items_text(remarks)}"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Version: {note.version}*  ·  {note.release_date}"},
        })
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{body}```"},
        })
        blocks.append({"type": "divider"})

    return blocks


def _simple_modal(title: str, message: str) -> dict:
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": title[:24]},
        "close": {"type": "plain_text", "text": "닫기"},
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": message}}],
    }

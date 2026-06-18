"""Slack Home Tab & Modal Block Kit 빌더"""
import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, and_


def html_to_mrkdwn(html: str) -> str:
    """HTML → Slack mrkdwn 변환 (<ul> 깊이 기반 들여쓰기)"""
    if not html:
        return ''
    # bold / code 먼저 변환 — bold 양쪽에 공백을 넣어 Slack word boundary 보장
    html = re.sub(r'<(strong|b)[^>]*>(.+?)</(strong|b)>', r' *\2* ', html, flags=re.DOTALL)
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
                indent = '    ' * (ul_depth - 1)
                result.append(f'\n{indent}- ')
            elif tag == 'br':
                result.append('\n')
            elif tag in ('p', 'div') and closing:
                result.append('\n')
        else:
            token = token.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            result.append(token)

    text = re.sub(r'\n{3,}', '\n\n', ''.join(result))
    text = re.sub(r'(?<=\S)[ \t]{2,}', ' ', text)  # bold 공백 삽입으로 생긴 연속 공백 정리 (줄 앞 들여쓰기 유지)
    return text.lstrip('\n').rstrip()


from models import (
    solution as sol_table, subscription as sub_table,
    customer_solutions as cs_table, customer_email as email_table,
    product as product_table, patchnote as patchnote_table,
    patchnote_feature, patchnote_improvement, patchnote_bugfix, patchnote_remark,
    customer_subscription_token as token_table, site_config as site_config_table,
    utility as utility_table, utility_subscription as util_sub_table,
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
        ).where(cs_table.c.customer_id == customer_id).order_by(sol_table.c.order, sol_table.c.id)
    ).fetchall()


def _get_subscribe_url(db: Session, customer_id: int) -> str:
    """Slack 버튼용 구독 페이지 URL. subscribe_base_url 미설정 또는 유효 토큰 없으면 빈 문자열."""
    cfg = db.execute(select(site_config_table).where(site_config_table.c.id == 1)).fetchone()
    subscribe_base = (cfg.subscribe_base_url or '').rstrip('/') if cfg else ''
    if not subscribe_base:
        return ''
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(token_table)
        .where(
            and_(
                token_table.c.customer_id == customer_id,
                token_table.c.expires_at > now,
            )
        )
        .order_by(token_table.c.expires_at.desc())
        .limit(1)
    ).fetchone()
    if not row:
        return ''
    return f"{subscribe_base}/{row.token}/"


def _get_patchnote_url(db: Session) -> str:
    cfg = db.execute(select(site_config_table).where(site_config_table.c.id == 1)).fetchone()
    return (cfg.patchnote_url or '').strip() if cfg else ''


def build_home_tab(db: Session, customer_id: int, customer_name: str) -> list:
    subscribe_url = _get_subscribe_url(db, customer_id)
    patchnote_url = _get_patchnote_url(db)

    global_actions = []
    if subscribe_url:
        global_actions.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "🌐 구독 설정"},
            "url": subscribe_url,
            "action_id": "open_subscribe_web",
        })
    global_actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "💬 Slack 채널 설정"},
        "action_id": "open_channel_settings_modal",
    })
    global_actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "📧 수신 이메일"},
        "action_id": "view_emails",
    })
    global_actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "📄 최근 패치노트"},
        "action_id": "view_all_patchnotes",
    })

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 Patch Notify 구독 관리"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"안녕하세요, *{customer_name}*님 👋"},
        },
        {
            "type": "actions",
            "elements": global_actions,
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": (
                "• *Gmail 구독* — 🌐 구독 설정 버튼으로 웹에서 솔루션별 이메일 알림을 설정하세요.\n"
                "• *Slack 알림* — 알림 채널에 `/invite @Patch Notify` 로 봇을 초대한 뒤 💬 Slack 채널 설정으로 채널을 등록하세요.\n"
                "• *패치노트 조회* — 📄 최근 패치노트를 누르면 DM으로 받아볼 수 있습니다."
            )}],
        },
        *([{
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "🔗 전체 패치노트 보기"},
                "url": patchnote_url,
                "action_id": "open_patchnote_web",
            }],
        }] if patchnote_url else []),
        {"type": "divider"},
    ]

    solutions = get_customer_solutions(db, customer_id)

    if not solutions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "⚠️ 구독 가능한 솔루션이 없습니다.\n담당자에게 문의해 주세요."},
        })
        return blocks

    sol_ids = [s.id for s in solutions]

    all_products = db.execute(
        select(product_table)
        .where(product_table.c.solution_id.in_(sol_ids))
        .order_by(product_table.c.order, product_table.c.platform, product_table.c.category)
    ).fetchall()
    products_by_sol: dict[int, list] = {}
    for p in all_products:
        products_by_sol.setdefault(p.solution_id, []).append(p)

    all_subs = db.execute(
        select(sub_table).where(sub_table.c.customer_id == customer_id)
    ).fetchall()
    sub_map: dict[tuple, object] = {(s.product_id, s.channel): s for s in all_subs}

    total_email_active = sum(1 for s in all_subs if s.channel == 'email' and s.is_active)
    total_slack_active = sum(1 for s in all_subs if s.channel == 'slack' and s.is_active)

    all_utilities = db.execute(
        select(utility_table).order_by(utility_table.c.order, utility_table.c.id)
    ).fetchall()
    all_util_subs = db.execute(
        select(util_sub_table).where(util_sub_table.c.customer_id == customer_id)
    ).fetchall()
    util_sub_map = {us.utility_id: us for us in all_util_subs}
    util_email_active = sum(1 for us in all_util_subs if us.is_active)
    util_slack_active = sum(1 for us in all_util_subs if us.is_active and us.slack_channel)

    summary_parts = [
        f"📦 솔루션 {len(solutions)}개",
        f"📧 이메일 {total_email_active}개 활성",
        f"💬 Slack {total_slack_active}개 활성",
    ]
    if all_utilities:
        summary_parts.append(f"🔧 유틸리티 {util_email_active}개 활성")

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "   |   ".join(summary_parts)}],
    })
    blocks.append({"type": "divider"})

    for sol in solutions:
        products = products_by_sol.get(sol.id, [])
        total = len(products)

        email_active = sum(
            1 for p in products
            if (s := sub_map.get((p.id, 'email'))) and s.is_active
        )
        slack_active = sum(
            1 for p in products
            if (s := sub_map.get((p.id, 'slack'))) and s.is_active
        )

        if total == 0:
            status_text = "_제품 없음_"
        else:
            email_text = f"✅ {email_active}/{total}개" if email_active else "❌ 비활성"
            slack_text = f"✅ {slack_active}/{total}개" if slack_active else "❌ 비활성"
            status_text = f"📧 {email_text}   💬 {slack_text}"

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"*{sol.name}*   {status_text}"}],
        })

    # 유틸리티 섹션
    if all_utilities:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*🔧 유틸리티*"},
        })
        for u in all_utilities:
            us = util_sub_map.get(u.id)
            email_status = "✅ 활성" if (us and us.is_active) else "❌ 비활성"
            slack_status = "✅ 활성" if (us and us.is_active and us.slack_channel) else "❌ 비활성"
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": (
                    f"*{u.name}*   📧 {email_status}   💬 {slack_status}"
                )}],
            })

    return blocks


def build_channel_settings_modal(db: Session, customer_id: int) -> dict:
    """전체 솔루션의 Slack 채널을 한 번에 설정하는 통합 모달"""
    solutions = get_customer_solutions(db, customer_id)
    if not solutions:
        return _simple_modal("Slack 채널 설정", "구독 가능한 솔루션이 없습니다.")

    sol_ids = [s.id for s in solutions]
    all_products = db.execute(
        select(product_table)
        .where(product_table.c.solution_id.in_(sol_ids))
        .order_by(product_table.c.order, product_table.c.platform, product_table.c.category)
    ).fetchall()
    products_by_sol: dict[int, list] = {}
    for p in all_products:
        products_by_sol.setdefault(p.solution_id, []).append(p)

    product_ids = [p.id for p in all_products]
    subs = db.execute(
        select(sub_table).where(
            and_(
                sub_table.c.customer_id == customer_id,
                sub_table.c.product_id.in_(product_ids),
                sub_table.c.channel == 'slack',
            )
        )
    ).fetchall()
    sub_map = {s.product_id: s for s in subs}

    blocks = []
    for sol in solutions:
        products = products_by_sol.get(sol.id, [])
        if not products:
            continue

        product_options = [
            {
                "text": {"type": "plain_text", "text": f"{_PLATFORM_LABEL.get(p.platform, p.platform)} {_CATEGORY_LABEL.get(p.category, p.category)}"},
                "value": str(p.id),
            }
            for p in products
        ]

        # 현재 채널 및 활성 제품
        slack_channel = ''
        active_opts = []
        for p, opt in zip(products, product_options):
            s = sub_map.get(p.id)
            if s and s.is_active:
                active_opts.append(opt)
                if s.slack_channel:
                    slack_channel = s.slack_channel

        channel_element = {
            "type": "conversations_select",
            "action_id": "slack_channel_value",
            "placeholder": {"type": "plain_text", "text": "채널 선택"},
            "filter": {"include": ["public"], "exclude_bot_users": True},
        }
        if slack_channel:
            channel_element["initial_conversation"] = slack_channel

        def _checkboxes(block_id, action_id, initial):
            el = {"type": "checkboxes", "action_id": action_id, "options": product_options}
            if initial:
                el["initial_options"] = initial
            return {
                "type": "input",
                "block_id": block_id,
                "label": {"type": "plain_text", "text": "알림 받을 제품"},
                "element": el,
                "optional": True,
            }

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{sol.name}*"}})
        blocks.append({
            "type": "input",
            "block_id": f"slack_channel_{sol.id}",
            "label": {"type": "plain_text", "text": "알림 채널"},
            "element": channel_element,
            "optional": True,
        })
        blocks.append(_checkboxes(f"slack_products_{sol.id}", "slack_products_select", active_opts))
        blocks.append({"type": "divider"})

    # 유틸리티 섹션
    utilities = db.execute(
        select(utility_table).order_by(utility_table.c.order, utility_table.c.id)
    ).fetchall()
    if utilities:
        util_subs = db.execute(
            select(util_sub_table).where(util_sub_table.c.customer_id == customer_id)
        ).fetchall()
        util_sub_map = {us.utility_id: us for us in util_subs}

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🔧 유틸리티*"}})
        for u in utilities:
            us = util_sub_map.get(u.id)
            active_option = {"text": {"type": "plain_text", "text": "활성화"}, "value": "1"}
            checkbox_el = {
                "type": "checkboxes",
                "action_id": "utility_active_select",
                "options": [active_option],
            }
            if us and us.is_active:
                checkbox_el["initial_options"] = [active_option]

            ch_el = {
                "type": "conversations_select",
                "action_id": "utility_channel_value",
                "placeholder": {"type": "plain_text", "text": "채널 선택"},
                "filter": {"include": ["public"], "exclude_bot_users": True},
            }
            if us and us.slack_channel:
                ch_el["initial_conversation"] = us.slack_channel

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": u.name}})
            blocks.append({
                "type": "input",
                "block_id": f"utility_active_{u.id}",
                "label": {"type": "plain_text", "text": "활성화"},
                "element": checkbox_el,
                "optional": True,
            })
            blocks.append({
                "type": "input",
                "block_id": f"utility_channel_{u.id}",
                "label": {"type": "plain_text", "text": "Slack 알림 채널"},
                "element": ch_el,
                "optional": True,
            })
            blocks.append({"type": "divider"})

    if not blocks:
        return _simple_modal("Slack 채널 설정", "등록된 제품 및 유틸리티가 없습니다.")

    return {
        "type": "modal",
        "callback_id": "save_channel_settings",
        "title": {"type": "plain_text", "text": "Slack 채널 설정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "private_metadata": str(customer_id),
        "blocks": blocks,
    }


def build_subscription_modal(db: Session, customer_id: int, solution_id: int, solution_name: str) -> dict:
    """솔루션 단위 구독 설정 모달 — 제품 선택 + 공통 설정"""
    products = db.execute(
        select(product_table).where(product_table.c.solution_id == solution_id)
        .order_by(product_table.c.order, product_table.c.platform, product_table.c.category)
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

    product_ids = [p.id for p in products]
    subs = db.execute(
        select(sub_table).where(
            and_(sub_table.c.customer_id == customer_id, sub_table.c.product_id.in_(product_ids))
        )
    ).fetchall()
    sub_map = {(s.product_id, s.channel): s for s in subs}

    # 현재 활성화된 제품 수집
    email_active_opts, slack_active_opts = [], []
    slack_channel = ''

    for p, opt in zip(products, product_options):
        email_sub = sub_map.get((p.id, 'email'))
        slack_sub = sub_map.get((p.id, 'slack'))
        if email_sub and email_sub.is_active:
            email_active_opts.append(opt)
        if slack_sub and slack_sub.is_active:
            slack_active_opts.append(opt)
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


def build_patchnote_select_modal(db: Session, customer_id: int) -> dict:
    """솔루션/제품을 한 모달에서 선택하는 최근 패치노트 조회 모달"""
    solutions = get_customer_solutions(db, customer_id)
    if not solutions:
        return _simple_modal("최근 패치노트", "구독 가능한 솔루션이 없습니다.")

    sol_ids = [s.id for s in solutions]
    all_products = db.execute(
        select(product_table)
        .where(product_table.c.solution_id.in_(sol_ids))
        .order_by(product_table.c.order, product_table.c.platform, product_table.c.category)
    ).fetchall()
    products_by_sol: dict[int, list] = {}
    for p in all_products:
        products_by_sol.setdefault(p.solution_id, []).append(p)

    option_groups = []
    for sol in solutions:
        products = products_by_sol.get(sol.id, [])
        if not products:
            continue
        option_groups.append({
            "label": {"type": "plain_text", "text": sol.name},
            "options": [
                {
                    "text": {"type": "plain_text", "text": f"{_PLATFORM_LABEL.get(p.platform, p.platform)} {_CATEGORY_LABEL.get(p.category, p.category)}"},
                    "value": f"{p.id}:{sol.name}",
                }
                for p in products
            ],
        })

    # 유틸리티 옵션 그룹 추가
    utilities = db.execute(
        select(utility_table).order_by(utility_table.c.order, utility_table.c.id)
    ).fetchall()
    if utilities:
        option_groups.append({
            "label": {"type": "plain_text", "text": "유틸리티"},
            "options": [
                {
                    "text": {"type": "plain_text", "text": u.name},
                    "value": f"u:{u.id}:{u.name}",
                }
                for u in utilities
            ],
        })

    if not option_groups:
        return _simple_modal("최근 패치노트", "등록된 제품이 없습니다.")

    return {
        "type": "modal",
        "callback_id": "select_patchnote_product",
        "title": {"type": "plain_text", "text": "최근 패치노트"},
        "submit": {"type": "plain_text", "text": "보기"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [{
            "type": "input",
            "block_id": "patchnote_product",
            "label": {"type": "plain_text", "text": "솔루션 / 유틸리티 선택"},
            "element": {
                "type": "static_select",
                "action_id": "product_id",
                "option_groups": option_groups,
                "placeholder": {"type": "plain_text", "text": "제품을 선택하세요"},
            },
        }],
    }


def build_product_select_modal(db: Session, solution_id: int, solution_name: str) -> dict:
    """패치노트 조회를 위한 제품 선택 모달"""
    products = db.execute(
        select(product_table).where(product_table.c.solution_id == solution_id)
        .order_by(product_table.c.order, product_table.c.platform, product_table.c.category)
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


def _html_to_rich_text_elements(html: str) -> list:
    """HTML → Slack rich_text block elements (bullet/ordered list, bold, code, link 지원)"""
    if not html:
        return []

    _links = {}

    def _strip_tags(s):
        return re.sub(r'<[^>]+>', '', s)

    def _sub_link(m):
        k = f'\x00L{len(_links)}\x00'
        t = _strip_tags(m.group(2)).strip() or m.group(1)
        _links[k] = (m.group(1), t)
        return k

    html = re.sub(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', _sub_link, html, flags=re.DOTALL)

    def _sub_md_link(m):
        k = f'\x00L{len(_links)}\x00'
        _links[k] = (m.group(2), m.group(1))
        return k

    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _sub_md_link, html)

    result = []
    list_styles = []
    li_stack = []
    li_starts = []
    pending = []
    top_inlines = []
    bold = 0
    code = 0

    def _dest():
        return li_stack[-1] if li_stack else top_inlines

    def _add_inline(text):
        if not text:
            return
        elem = {'type': 'text', 'text': text}
        s = {}
        if bold: s['bold'] = True
        if code: s['code'] = True
        if s: elem['style'] = s
        _dest().append(elem)

    def _add_text(raw):
        raw = raw.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        for p in re.split(r'(\x00L\d+\x00)', raw):
            if not p:
                continue
            if p in _links:
                url, text = _links[p]
                elem = {'type': 'link', 'url': url, 'text': text}
                if bold:
                    elem['style'] = {'bold': True}
                _dest().append(elem)
            else:
                p = p.strip('\n\r\t')
                if p:
                    _add_inline(p)

    def _flush_top():
        clean = [e for e in top_inlines if e]
        if clean:
            result.append({'type': 'rich_text_section', 'elements': clean})
        top_inlines.clear()

    def _flush_pending():
        if not pending:
            return
        i = 0
        while i < len(pending):
            depth, style, elems = pending[i]
            items = [elems]
            j = i + 1
            while j < len(pending) and pending[j][0] == depth and pending[j][1] == style:
                items.append(pending[j][2])
                j += 1
            result.append({
                'type': 'rich_text_list',
                'style': style,
                'indent': depth,
                'elements': [{'type': 'rich_text_section', 'elements': e} for e in items],
            })
            i = j
        pending.clear()

    for token in re.split(r'(</?[a-zA-Z][^>]*>)', html):
        if not token:
            continue
        m = re.match(r'^<(/?)(\w+)', token)
        if not m:
            _add_text(token)
            continue
        closing = m.group(1) == '/'
        tag = m.group(2).lower()

        if tag == 'ul' and not closing:
            if not list_styles:
                _flush_top()
            list_styles.append('bullet')
        elif tag == 'ol' and not closing:
            if not list_styles:
                _flush_top()
            list_styles.append('ordered')
        elif tag in ('ul', 'ol') and closing:
            if list_styles:
                list_styles.pop()
            if not list_styles:
                _flush_pending()
        elif tag == 'li' and not closing:
            li_stack.append([])
            li_starts.append(len(pending))
        elif tag == 'li' and closing:
            if li_stack:
                inlines = li_stack.pop()
                start = li_starts.pop() if li_starts else len(pending)
                if list_styles:
                    clean = [e for e in inlines if e]
                    if clean:
                        pending.insert(start, (len(list_styles) - 1, list_styles[-1], clean))
        elif tag in ('strong', 'b') and not closing:
            bold += 1
        elif tag in ('strong', 'b') and closing:
            bold = max(0, bold - 1)
        elif tag == 'code' and not closing:
            code += 1
        elif tag == 'code' and closing:
            code = max(0, code - 1)
        elif tag == 'br':
            _dest().append({'type': 'text', 'text': '\n'})

    _flush_pending()
    _flush_top()
    return result


def _items_rich_text_elements(rows) -> list:
    elements = []
    for r in rows:
        elements.extend(_html_to_rich_text_elements(r.content))
    return elements


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

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Version: {note.version}*  ·  {note.release_date}"},
        })

        body = (
            f"[Patch Note]\n"
            f"기능 추가\n{_items_text(features)}\n\n"
            f"기능 개선\n{_items_text(improves)}\n\n"
            f"버그 수정\n{_items_text(bugfixes)}"
        )
        if len(body) > 2990:
            body = body[:2987] + "…"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```{body}```"}})

        if remarks:
            rt_elements = _items_rich_text_elements(remarks)
            if rt_elements:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Remarks*"}})
                blocks.append({"type": "rich_text", "elements": rt_elements})

        blocks.append({"type": "divider"})

    return blocks


def build_utility_patchnote_blocks(db: Session, utility_id: int, utility_name: str) -> list:
    """유틸리티의 최근 3개 패치노트를 메시지 블록으로 반환"""
    notes = db.execute(
        select(patchnote_table)
        .where(
            and_(
                patchnote_table.c.utility_id == utility_id,
                patchnote_table.c.is_published == True,
            )
        )
        .order_by(patchnote_table.c.release_date.desc())
        .limit(3)
    ).fetchall()

    if not notes:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "등록된 패치노트가 없습니다."}}]

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"{utility_name} 최근 패치노트"}}]

    for note in notes:
        features = _fetch_items(db, patchnote_feature, note.id)
        improves = _fetch_items(db, patchnote_improvement, note.id)
        bugfixes = _fetch_items(db, patchnote_bugfix, note.id)
        remarks  = _fetch_items(db, patchnote_remark, note.id)

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Version: {note.version}*  ·  {note.release_date}"},
        })

        body = (
            f"[Patch Note]\n"
            f"기능 추가\n{_items_text(features)}\n\n"
            f"기능 개선\n{_items_text(improves)}\n\n"
            f"버그 수정\n{_items_text(bugfixes)}"
        )
        if len(body) > 2990:
            body = body[:2987] + "…"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```{body}```"}})

        if remarks:
            rt_elements = _items_rich_text_elements(remarks)
            if rt_elements:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Remarks*"}})
                blocks.append({"type": "rich_text", "elements": rt_elements})

        blocks.append({"type": "divider"})

    return blocks


def build_email_modal(db: Session, customer_id: int) -> dict:
    """수신 이메일 목록을 보여주는 모달"""
    emails = db.execute(
        select(email_table).where(email_table.c.customer_id == customer_id)
    ).fetchall()

    if not emails:
        message = "등록된 수신 이메일이 없습니다.\n담당자에게 문의해 주세요."
    else:
        message = '\n'.join(
            f"• {r.email}" + (f"  ({r.name})" if r.name else "")
            for r in emails
        )

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "수신 이메일 목록"},
        "close": {"type": "plain_text", "text": "닫기"},
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": message}}],
    }


def _simple_modal(title: str, message: str) -> dict:
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": title[:24]},
        "close": {"type": "plain_text", "text": "닫기"},
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": message}}],
    }

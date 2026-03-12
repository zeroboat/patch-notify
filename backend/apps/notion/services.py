"""
Notion 페이지에서 패치노트를 가져와 DB에 동기화하는 서비스 모듈

흐름: Notion API → Markdown → HTML 파싱 → DB upsert
"""

import re
import logging

import requests
from django.conf import settings

from apps.patchnote.models import PatchNote, Feature, Improvement, BugFix, Remark
from .models import NotionPageMapping

logger = logging.getLogger(__name__)

NOTION_API_VERSION = '2026-03-11'

# ──────────────────────────────────────────────
# 섹션명 → 키 매핑
# ──────────────────────────────────────────────

SECTION_MAP = {
    '기능 추가': 'new_features',
    '기능 개선': 'improvements',
    '버그 수정': 'bug_fixes',
    'Feature Additions': 'new_features',
    'Feature Improvements': 'improvements',
    'Bug Fixes': 'bug_fixes',
    'Added features': 'new_features',
    'Added Features': 'new_features',
    'New Features': 'new_features',
    'New Feactures': 'new_features',
    'Improved Features': 'improvements',
    'Feature improvement': 'improvements',
    'Improvements': 'improvements',
    'Enhancements': 'improvements',
    'Bug fixes': 'bug_fixes',
    'Bug Fixeds': 'bug_fixes',
}


# ──────────────────────────────────────────────
# 1. Notion API: 페이지 → Markdown
# ──────────────────────────────────────────────

def _get_notion_headers():
    return {
        'Authorization': f'Bearer {settings.NOTION_TOKEN}',
        'Notion-Version': NOTION_API_VERSION,
        'Content-Type': 'application/json',
    }


def fetch_page_markdown(page_id: str) -> str:
    """Notion 페이지 ID로 마크다운을 가져온다."""
    url = f'https://api.notion.com/v1/pages/{page_id}/markdown'
    res = requests.get(url, headers=_get_notion_headers(), timeout=30)
    res.raise_for_status()
    data = res.json()
    md = data.get('markdown', data) if isinstance(data, dict) else data
    if isinstance(md, dict):
        md = md.get('markdown', '')
    return md


# ──────────────────────────────────────────────
# 2. Notion Markdown 정리
# ──────────────────────────────────────────────

def _clean_notion_md(md: str) -> str:
    """Notion 고유 태그 제거 및 마크다운 정규화"""
    raw_lines = md.split('\n')

    # 코드 블록 외부 탭 기준 계산
    in_code = False
    tab_counts = []
    for line in raw_lines:
        if re.match(r'^\t*`{3}', line):
            in_code = not in_code
        elif not in_code and line.strip():
            m = re.match(r'^(\t+)', line)
            if m:
                tab_counts.append(len(m.group(1)))
    base_tabs = min(tab_counts) if tab_counts else 0

    lines = []
    in_code = False
    for line in raw_lines:
        if re.match(r'^\t*`{3}', line):
            in_code = not in_code
            lines.append(re.sub(r'^\t+', '', line))
        elif in_code:
            lines.append(line.replace('\t', '  '))
        else:
            m = re.match(r'^(\t*)(.*)', line)
            extra = max(0, len(m.group(1)) - base_tabs)
            lines.append('  ' * extra + m.group(2))
    md = '\n'.join(lines)

    md = md.replace('<br>', '\n')
    md = md.replace('&nbsp;', ' ')
    md = re.sub(r'^<span[^>]*>(.*?)</span>', r'# \1', md, count=1)
    md = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', md)

    def callout_to_quote(m):
        inner = m.group(1).strip()
        return '\n'.join(f'> {line}' for line in inner.split('\n'))
    md = re.sub(r'::: callout[^\n]*\n(.*?):::', callout_to_quote, md, flags=re.DOTALL)

    for tag in [r'<columns>', r'</columns>', r'<column>', r'</column>',
                r'<table_of_contents[^/]*/>', r'<empty-block\s*/>']:
        md = re.sub(tag + r'[ \t]*\n?', '', md)

    md = re.sub(r'<mention-page url="([^"]+)"/>', r'[\1](\1)', md)
    md = md.replace('\\[', '[').replace('\\]', ']')

    lang_map = {'plain text': '', 'javascript': 'sh', 'groovy': 'groovy'}
    def replace_code_open(m):
        return f'```{lang_map.get(m.group(1), m.group(1))}\n'
    md = re.sub(
        r'^`{1,3}(' + '|'.join(re.escape(k) for k in lang_map) + r')\n',
        replace_code_open, md, flags=re.MULTILINE,
    )
    md = re.sub(r'^`{1,2}$', '```', md, flags=re.MULTILINE)
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = '\n'.join(line.rstrip() for line in md.split('\n'))

    return md.strip() + '\n'


# ──────────────────────────────────────────────
# 3. Markdown → HTML 파싱
# ──────────────────────────────────────────────

def _md_inline_to_html(text: str) -> str:
    """인라인 마크다운 → HTML 변환 (code 블록 내부는 보존)"""
    parts = re.split(r'(<pre><code>[\s\S]*?</code></pre>)', text)
    for i, part in enumerate(parts):
        if part.startswith('<pre><code>'):
            continue
        part = re.sub(r'`([^`]+)`', r'<code>\1</code>', part)
        segs = re.split(r'(<code>[\s\S]*?</code>)', part)
        for j, seg in enumerate(segs):
            if not seg.startswith('<code>'):
                seg = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', seg)
                seg = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', seg)
                segs[j] = seg
        parts[i] = ''.join(segs)
    return ''.join(parts)


def _get_indent(line: str) -> int:
    spaces = len(line) - len(line.lstrip(' '))
    tabs = len(line) - len(line.lstrip('\t'))
    return spaces + tabs * 2


def _parse_bullets(lines: list[str]) -> list:
    """인덴트 기반 불릿 파싱 (코드 블록 포함)"""
    bullet_indents = [_get_indent(l) for l in lines if l.strip().startswith('- ')]
    if not bullet_indents:
        return []
    base_indent = min(bullet_indents)

    result = []
    stack = [(base_indent - 1, result)]
    last_item = None
    in_code = False
    code_lines = []

    for line in lines:
        stripped = line.strip()

        if re.match(r'^`{3}', stripped):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                in_code = False
                code_html = '<pre><code>' + '\n'.join(code_lines).strip() + '</code></pre>'
                if last_item is not None:
                    last_item['text'] += code_html
            continue

        if in_code:
            code_lines.append(line.replace('\t', '  '))
            continue

        if not stripped:
            continue

        if not stripped.startswith('- '):
            if last_item is not None:
                last_item['text'] += ' ' + stripped
            continue

        indent = _get_indent(line)
        item = {'text': stripped[2:], 'subs': []}

        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        stack[-1][1].append(item)
        stack.append((indent, item['subs']))
        last_item = item

    return result


def _items_to_html(items: list) -> str:
    filtered = [i for i in items if i['text'].strip().upper() != 'N/A' and i['text'].strip()]
    if not filtered:
        return ''
    parts = []
    for item in filtered:
        text = _md_inline_to_html(item['text'])
        if item['subs']:
            parts.append(f'<li>{text}{_items_to_html(item["subs"])}</li>')
        else:
            parts.append(f'<li>{text}</li>')
    return '<ul>' + ''.join(parts) + '</ul>'


def _parse_code_block(code: str) -> dict:
    sections = {'new_features': '', 'improvements': '', 'bug_fixes': ''}
    current_key = None
    current_lines = []

    for line in code.split('\n'):
        stripped = line.strip()
        if stripped in SECTION_MAP:
            if current_key:
                sections[current_key] = _items_to_html(_parse_bullets(current_lines))
            current_key = SECTION_MAP[stripped]
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key:
        sections[current_key] = _items_to_html(_parse_bullets(current_lines))

    return sections


def _parse_remarks(block: str) -> str:
    match = re.search(r'\*\[\*Remarks\*\]\*\*\n(.*?)$', block, re.DOTALL)
    if not match:
        return ''
    raw = match.group(1)
    end = re.search(r'\n\s*##\s+', raw)
    if end:
        raw = raw[:end.start()]
    lines = raw.split('\n')
    return _items_to_html(_parse_bullets(lines))


def parse_md_to_patch_notes(md: str) -> list[dict]:
    """마크다운을 버전별 패치노트 dict 리스트로 파싱"""
    blocks = re.split(r'\n\s*---+\s*\n|\n(?=\s*##\s+\S)', md)
    patch_notes = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        version_match = re.search(r'^\s*##\s+(\S+)', block, re.MULTILINE)
        if not version_match:
            continue

        version = version_match.group(1)
        date_match = re.search(r'(?:RELEASE\s+)?DATE\s*:\s*(\d{4}-\d{2}-\d{2})', block)
        patch_date = date_match.group(1) if date_match else ''

        code_match = re.search(r'```[^\n]*\n(.*?)```', block, re.DOTALL)
        sections = _parse_code_block(code_match.group(1)) if code_match else {
            'new_features': '', 'improvements': '', 'bug_fixes': ''
        }

        patch_notes.append({
            'version': version,
            'patch_date': patch_date,
            'new_features': sections['new_features'],
            'improvements': sections['improvements'],
            'bug_fixes': sections['bug_fixes'],
            'special_notes': _parse_remarks(block),
        })

    return patch_notes


# ──────────────────────────────────────────────
# 4. DB 저장 (upsert)
# ──────────────────────────────────────────────

def _save_section(patch_note, html_ko, html_en, model_class):
    """섹션 HTML을 DB에 저장 (빈 내용은 건너뜀)"""
    html_ko = (html_ko or '').strip()
    html_en = (html_en or '').strip()
    if not html_ko and not html_en:
        return
    text_only = re.sub(r'<[^>]+>', '', html_ko).replace('\xa0', '').replace('&nbsp;', '').strip()
    if not text_only and not html_en:
        return
    model_class.objects.create(
        patch_note=patch_note,
        content=html_ko or '',
        content_en=html_en or None,
        order=0,
    )


# ──────────────────────────────────────────────
# 5. 메인 동기화 함수
# ──────────────────────────────────────────────

def sync_product(mapping: NotionPageMapping, version: str = None) -> dict:
    """
    특정 Product의 Notion 페이지를 동기화한다.

    Args:
        mapping: NotionPageMapping 인스턴스
        version: 특정 버전만 동기화 (None이면 전체)

    Returns:
        {'created': int, 'updated': int, 'skipped': int}
    """
    product = mapping.product
    stats = {'created': 0, 'updated': 0, 'skipped': 0}

    # 한국어 MD 가져오기
    md_ko = fetch_page_markdown(mapping.page_id_ko)
    md_ko = _clean_notion_md(md_ko)
    notes_ko = parse_md_to_patch_notes(md_ko)

    # 영문 MD (있으면)
    notes_en_by_version = {}
    if mapping.page_id_en:
        try:
            md_en = fetch_page_markdown(mapping.page_id_en)
            md_en = _clean_notion_md(md_en)
            for note in parse_md_to_patch_notes(md_en):
                notes_en_by_version[note['version']] = note
        except Exception as e:
            logger.warning(f'영문 페이지 로드 실패 ({mapping.page_id_en}): {e}')

    for note_data in notes_ko:
        v = note_data.get('version', '').strip()
        patch_date = note_data.get('patch_date', '').strip()

        if not v or not patch_date:
            stats['skipped'] += 1
            continue

        # 특정 버전 필터
        if version and v != version:
            continue

        en = notes_en_by_version.get(v, {})

        patch_note, created = PatchNote.objects.get_or_create(
            product=product,
            version=v,
            defaults={'release_date': patch_date},
        )

        if not created:
            # 기존 데이터 삭제 후 재등록
            patch_note.release_date = patch_date
            patch_note.save()
            patch_note.features.all().delete()
            patch_note.improvements.all().delete()
            patch_note.bugfixes.all().delete()
            patch_note.remarks.all().delete()
            stats['updated'] += 1
        else:
            stats['created'] += 1

        _save_section(patch_note, note_data.get('new_features'), en.get('new_features'), Feature)
        _save_section(patch_note, note_data.get('improvements'), en.get('improvements'), Improvement)
        _save_section(patch_note, note_data.get('bug_fixes'), en.get('bug_fixes'), BugFix)
        _save_section(patch_note, note_data.get('special_notes'), en.get('special_notes'), Remark)

    return stats


# ──────────────────────────────────────────────
# 6. HTML → Markdown 역변환
# ──────────────────────────────────────────────

def _html_to_md_inline(html: str) -> str:
    """인라인 HTML 태그를 마크다운으로 역변환"""
    # <strong> → **
    html = re.sub(r'<strong>(.*?)</strong>', r'**\1**', html)
    # <code> (인라인) → `
    html = re.sub(r'<code>(.*?)</code>', r'`\1`', html)
    # <a href="url">text</a> → [text](url)
    html = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', html)
    return html


def _html_to_md_bullets(html: str, indent: int = 0) -> str:
    """<ul><li> 구조를 마크다운 bullet 리스트로 역변환"""
    if not html or not html.strip():
        return ''

    lines = []
    prefix = '  ' * indent

    # <pre><code>...</code></pre> 블록을 플레이스홀더로 보호
    code_blocks = []
    def save_code(m):
        code_blocks.append(m.group(1))
        return f'__CODE_BLOCK_{len(code_blocks) - 1}__'
    html = re.sub(r'<pre><code[^>]*>([\s\S]*?)</code></pre>', save_code, html)

    # 중첩 <ul>을 분리하기 위해 단계별 처리
    # 먼저 최외곽 <ul> 제거
    inner = re.sub(r'^<ul>([\s\S]*)</ul>$', r'\1', html.strip())

    # <li> 단위로 분리 (중첩 고려)
    items = _split_li_items(inner)

    for item_html in items:
        # 하위 <ul> 분리
        sub_match = re.search(r'<ul>([\s\S]*)</ul>', item_html)
        if sub_match:
            text_part = item_html[:sub_match.start()].strip()
            sub_html = '<ul>' + sub_match.group(1) + '</ul>'
        else:
            text_part = item_html.strip()
            sub_html = ''

        # 코드 블록 플레이스홀더 복원 (bullet 텍스트 내)
        for idx, code in enumerate(code_blocks):
            placeholder = f'__CODE_BLOCK_{idx}__'
            if placeholder in text_part:
                text_part = text_part.replace(placeholder, '')
                # 코드 블록은 bullet 아래에 별도 줄로
                text_md = _html_to_md_inline(text_part)
                lines.append(f'{prefix}- {text_md}')
                lines.append(f'{prefix}  ```')
                for code_line in code.strip().split('\n'):
                    lines.append(f'{prefix}  {code_line}')
                lines.append(f'{prefix}  ```')
                if sub_html:
                    lines.append(_html_to_md_bullets(sub_html, indent + 1))
                break
        else:
            text_md = _html_to_md_inline(text_part)
            if text_md.strip():
                lines.append(f'{prefix}- {text_md}')
            if sub_html:
                lines.append(_html_to_md_bullets(sub_html, indent + 1))

    return '\n'.join(lines)


def _split_li_items(inner_html: str) -> list[str]:
    """<li>...</li> 항목을 중첩 태그를 고려하여 분리"""
    items = []
    depth = 0
    current = []
    # <li> 와 </li> 기준으로 분리
    parts = re.split(r'(</?li>|</?ul>)', inner_html)

    in_item = False
    for part in parts:
        if part == '<li>':
            if depth == 0:
                in_item = True
                current = []
            else:
                current.append(part)
            depth += 1
        elif part == '</li>':
            depth -= 1
            if depth == 0:
                items.append(''.join(current))
                in_item = False
            else:
                current.append(part)
        elif in_item:
            current.append(part)

    return items


def _section_to_md_bullets(manager) -> str:
    """DB 섹션 매니저에서 HTML을 가져와 MD bullet로 변환"""
    obj = manager.filter(parent__isnull=True).order_by('order', 'id').first()
    if not obj or not obj.content.strip():
        return '- N/A'
    return _html_to_md_bullets(obj.content) or '- N/A'


def patch_note_to_md(patch_note: PatchNote) -> str:
    """PatchNote 인스턴스를 Notion 원본 MD 형식으로 변환 (push용)"""
    features_md = _section_to_md_bullets(patch_note.features)
    improvements_md = _section_to_md_bullets(patch_note.improvements)
    bugfixes_md = _section_to_md_bullets(patch_note.bugfixes)
    remarks_md = _section_to_md_bullets(patch_note.remarks)

    # remarks 각 줄에 탭 프리픽스
    remarks_tabbed = '\n'.join(
        '\t\t' + line if line.strip() else line
        for line in remarks_md.split('\n')
    )

    lines = [
        f'\t\t## <span color="green_bg">{patch_note.version} </span>',
        f'\t\tDATE : {patch_note.release_date}',
        '\t\t**\\[*Patch notes*\\]**',
        '\t\t```plain text',
        '기능 추가',
        features_md,
        '',
        '기능 개선',
        improvements_md,
        '',
        '버그 수정',
        bugfixes_md,
        '\t\t```',
        '\t\t**\\[*Remarks*\\]**',
        remarks_tabbed,
        '\t\t<empty-block/>',
        '\t\t---',
    ]
    return '\n'.join(lines)


# ──────────────────────────────────────────────
# 7. Notion에 패치노트 Push
# ──────────────────────────────────────────────

def _notion_update_markdown(page_id: str, payload: dict):
    """Notion Markdown API에 PATCH 요청"""
    url = f'https://api.notion.com/v1/pages/{page_id}/markdown'
    res = requests.patch(url, headers=_get_notion_headers(), json=payload, timeout=30)
    res.raise_for_status()
    return res.json()


def push_patch_note_to_notion(patch_note: PatchNote, is_new: bool = True) -> dict:
    """
    패치노트를 Notion 페이지에 push한다.

    Args:
        patch_note: PatchNote 인스턴스
        is_new: True면 insert_content, False면 update_content (기존 버전 수정)

    Returns:
        Notion API 응답
    """
    if not settings.NOTION_ENABLED or not settings.NOTION_TOKEN:
        raise ValueError('Notion 연동이 비활성화되어 있습니다.')

    try:
        mapping = NotionPageMapping.objects.get(product=patch_note.product)
    except NotionPageMapping.DoesNotExist:
        raise ValueError('해당 제품의 Notion 매핑 정보가 없습니다.')

    md_content = patch_note_to_md(patch_note)

    if is_new:
        # 새 버전: 앵커 텍스트를 찾아서 앵커 + 새 콘텐츠로 교체 (insert 효과)
        anchor = '# 지원중인 버전'
        payload = {
            'type': 'update_content',
            'update_content': {
                'content_updates': [
                    {
                        'old_str': anchor,
                        'new_str': anchor + '\n' + md_content,
                    }
                ],
            },
        }
    else:
        # 기존 버전 수정: search & replace
        current_md = fetch_page_markdown(mapping.page_id_ko)
        version = patch_note.version

        # Notion 원본 형식에서 버전 블록 추출 (탭, span 태그 포함)
        pattern = re.compile(
            rf'(\t*##\s+(?:<span[^>]*>)?{re.escape(version)}\s*(?:</span>)?[\s\S]*?)(---\s*\n|(?=\t*##\s)|$)'
        )
        match = pattern.search(current_md)
        if not match:
            raise ValueError(f'Notion 페이지에서 버전 {version}을 찾을 수 없습니다.')

        old_block = match.group(0).rstrip()
        payload = {
            'type': 'update_content',
            'update_content': {
                'content_updates': [
                    {
                        'old_str': old_block,
                        'new_str': md_content,
                    }
                ],
            },
        }

    result = _notion_update_markdown(mapping.page_id_ko, payload)
    logger.info(f'Notion push 완료: {patch_note.product} v{patch_note.version} ({"insert" if is_new else "update"})')
    return result

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

NOTION_API_VERSION = '2025-09-03'

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
        r'^`{{1,3}}(' + '|'.join(re.escape(k) for k in lang_map) + r')\n',
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

        code_match = re.search(r'```\n(.*?)```', block, re.DOTALL)
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

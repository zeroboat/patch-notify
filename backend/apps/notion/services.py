"""
Notion 페이지에서 패치노트를 가져와 DB에 동기화하는 서비스 모듈

흐름: Notion API → Markdown 파일 저장 → HTML 파싱 → DB upsert
변경 감지: Notion last_edited_time과 저장된 MD 파일 비교
"""

import re
import logging
from datetime import datetime
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

from apps.patchnote.models import PatchNote, Feature, Improvement, BugFix, Remark
from .models import NotionPageMapping

logger = logging.getLogger(__name__)

NOTION_API_VERSION = '2026-03-11'

# ──────────────────────────────────────────────
# 섹션명 → 키 매핑
# ──────────────────────────────────────────────

SECTION_MAP = {
    # 한국어
    '기능 추가': 'new_features',
    '기능 개선': 'improvements',
    '버그 수정': 'bug_fixes',
    '기능 수정': 'improvements',
    '기타': 'improvements',
    '보안 개선': 'improvements',
    '가이드': 'improvements',
    '기능 개선 및 변경 사항': 'improvements',
    '변경 사항': 'improvements',
    '버그 수': 'bug_fixes',               # 오타 (버그 수정)
    # 영문 표준
    'Feature Additions': 'new_features',
    'Feature Improvements': 'improvements',
    'Bug Fixes': 'bug_fixes',
    # 영문 변형
    'Added features': 'new_features',
    'Added Features': 'new_features',
    'New Features': 'new_features',
    'New Feactures': 'new_features',       # 오타
    'Feature Addition': 'new_features',    # 단수형
    'Feature Improvement': 'improvements', # 단수형
    'Improved Features': 'improvements',
    'Improvements': 'improvements',
    'Enhancements': 'improvements',
    'Bug fixes': 'bug_fixes',
    'Bug Fixeds': 'bug_fixes',             # 오타
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


def fetch_page_metadata(page_id: str) -> dict:
    """Notion 페이지 메타데이터를 가져온다 (last_edited_time 등)."""
    url = f'https://api.notion.com/v1/pages/{page_id}'
    res = requests.get(url, headers=_get_notion_headers(), timeout=30)
    res.raise_for_status()
    return res.json()


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
# 1-1. MD 파일 저장/로드
# ──────────────────────────────────────────────

def _get_md_dir(product) -> Path:
    """제품별 MD 저장 디렉토리"""
    solution_name = product.solution.name.replace(' ', '_')
    return Path(settings.NOTION_MD_DIR) / solution_name


def _get_md_filename(product, lang: str = 'ko') -> str:
    """파일명 생성: {Platform}_{Category}[_en].md"""
    platform = product.get_platform_display().replace(' ', '_')
    category = product.get_category_display().replace(' ', '_')
    suffix = '_en' if lang == 'en' else ''
    return f'{platform}_{category}{suffix}.md'


def _save_md_file(product, md_content: str, lang: str = 'ko') -> Path:
    """cleaned MD를 파일로 저장"""
    md_dir = _get_md_dir(product)
    md_dir.mkdir(parents=True, exist_ok=True)
    file_path = md_dir / _get_md_filename(product, lang)
    file_path.write_text(md_content, encoding='utf-8')
    logger.info('MD 파일 저장: %s', file_path)
    return file_path


def _load_md_file(product, lang: str = 'ko') -> str | None:
    """저장된 MD 파일 로드 (없으면 None)"""
    file_path = _get_md_dir(product) / _get_md_filename(product, lang)
    if file_path.exists():
        return file_path.read_text(encoding='utf-8')
    return None


def _parse_notion_datetime(iso_str: str) -> datetime:
    """Notion ISO 8601 문자열을 datetime으로 변환"""
    return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))


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
    result = ''.join(parts)
    # bold가 code 경계에서 끊겨 잔존하는 ** 제거 (정상 bold는 이미 <strong> 변환됨)
    result = re.sub(r'\*{2,}', '', result)
    # Notion 색상 어노테이션 제거 ({color="red"} 등)
    result = re.sub(r'\s*\{color="[^"]*"\}', '', result)
    return result


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
    filtered = [i for i in items if re.sub(r'[*`_~.]+', '', i['text']).strip().upper() != 'N/A' and i['text'].strip()]
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
    match = re.search(r'\*{2,3}\[?\*?Remarks\*?\]?\*{2,3}\n(.*?)$', block, re.DOTALL)
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
        date_match = re.search(r'(?:RELEASE\s+)?DATE\s*:\s*(\d{4}-\d{2}(?:-\d{2})?)', block)
        patch_date = date_match.group(1) if date_match else ''
        if patch_date and len(patch_date) == 7:  # YYYY-MM → YYYY-MM-01
            patch_date += '-01'

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

def _check_page_changed(mapping, page_id: str, lang: str) -> tuple[bool, datetime | None]:
    """
    Notion 페이지가 마지막 동기화 이후 변경되었는지 확인.
    Returns: (changed: bool, last_edited: datetime | None)
    """
    try:
        meta = fetch_page_metadata(page_id)
        last_edited = _parse_notion_datetime(meta['last_edited_time'])
    except Exception as e:
        logger.warning('페이지 메타데이터 조회 실패 (%s): %s', page_id, e)
        return True, None  # 확인 불가 → 변경된 것으로 간주

    stored = mapping.notion_last_edited_ko if lang == 'ko' else mapping.notion_last_edited_en
    if stored and last_edited <= stored:
        logger.info('변경 없음 (%s %s): last_edited=%s, stored=%s', mapping.product, lang, last_edited, stored)
        return False, last_edited

    return True, last_edited


def _fetch_and_save_md(mapping, page_id: str, lang: str) -> tuple[str, bool]:
    """
    Notion에서 MD를 가져와 정리 후 파일 저장.
    저장된 파일과 내용이 동일하면 스킵.
    Returns: (cleaned_md, content_changed)
    """
    raw_md = fetch_page_markdown(page_id)
    cleaned_md = _clean_notion_md(raw_md)

    # 기존 파일과 비교
    existing = _load_md_file(mapping.product, lang)
    if existing == cleaned_md:
        logger.info('MD 내용 동일 (%s %s) — 파일 스킵', mapping.product, lang)
        return cleaned_md, False

    _save_md_file(mapping.product, cleaned_md, lang)
    return cleaned_md, True


def sync_product(mapping: NotionPageMapping, version: str = None, force: bool = False) -> dict:
    """
    특정 Product의 Notion 페이지를 동기화한다.

    Args:
        mapping: NotionPageMapping 인스턴스
        version: 특정 버전만 동기화 (None이면 전체)
        force: True면 변경 감지 무시하고 강제 동기화

    Returns:
        {'created': int, 'updated': int, 'skipped': int, 'unchanged': bool}
    """
    product = mapping.product
    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'unchanged': False}

    # ── 한국어 페이지 변경 감지 ──
    ko_changed = True
    ko_last_edited = None
    if not force:
        ko_changed, ko_last_edited = _check_page_changed(mapping, mapping.page_id_ko, 'ko')

    en_changed = False
    en_last_edited = None
    if mapping.page_id_en and not force:
        en_changed, en_last_edited = _check_page_changed(mapping, mapping.page_id_en, 'en')

    if not force and not ko_changed and not en_changed:
        stats['unchanged'] = True
        return stats

    # ── 한국어 MD 가져오기 & 파일 저장 ──
    if force or ko_changed:
        md_ko, ko_content_changed = _fetch_and_save_md(mapping, mapping.page_id_ko, 'ko')
    else:
        # 메타데이터상 변경 없지만 영문이 변경됨 → 기존 파일에서 로드
        md_ko = _load_md_file(product, 'ko')
        if not md_ko:
            md_ko, ko_content_changed = _fetch_and_save_md(mapping, mapping.page_id_ko, 'ko')
        else:
            ko_content_changed = False

    notes_ko = parse_md_to_patch_notes(md_ko)
    logger.info('%s 파싱된 버전 수: %d', product, len(notes_ko))

    # ── 영문 MD (있으면) ──
    notes_en_by_version = {}
    en_content_changed = False
    if mapping.page_id_en:
        try:
            if force or en_changed:
                md_en, en_content_changed = _fetch_and_save_md(mapping, mapping.page_id_en, 'en')
            else:
                md_en = _load_md_file(product, 'en')
                if not md_en:
                    md_en, en_content_changed = _fetch_and_save_md(mapping, mapping.page_id_en, 'en')

            if md_en:
                for note in parse_md_to_patch_notes(md_en):
                    notes_en_by_version[note['version']] = note
        except Exception as e:
            logger.warning('영문 페이지 로드 실패 (%s): %s', mapping.page_id_en, e)

    # ── 파일 내용도 동일하면 DB 업데이트 스킵 ──
    if not force and not ko_content_changed and not en_content_changed:
        logger.info('%s MD 파일 내용 변경 없음 — DB 업데이트 스킵', product)
        # last_edited 타임스탬프만 갱신
        if ko_last_edited:
            mapping.notion_last_edited_ko = ko_last_edited
        if en_last_edited:
            mapping.notion_last_edited_en = en_last_edited
        mapping.last_synced_at = timezone.now()
        mapping.save(update_fields=['notion_last_edited_ko', 'notion_last_edited_en', 'last_synced_at'])
        stats['unchanged'] = True
        return stats

    # ── DB upsert ──
    for note_data in notes_ko:
        v = note_data.get('version', '').strip()
        patch_date = note_data.get('patch_date', '').strip()

        if not v or not patch_date:
            stats['skipped'] += 1
            continue

        if version and v != version:
            continue

        en = notes_en_by_version.get(v, {})

        patch_note, created = PatchNote.objects.get_or_create(
            product=product,
            version=v,
            defaults={'release_date': patch_date},
        )

        if not created:
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

        if en:
            patch_note.translation_status = 'done'
        else:
            patch_note.translation_status = 'skipped'
        patch_note.save(update_fields=['translation_status', 'updated_at'])

    # ── 동기화 타임스탬프 갱신 ──
    if ko_last_edited:
        mapping.notion_last_edited_ko = ko_last_edited
    if en_last_edited:
        mapping.notion_last_edited_en = en_last_edited
    mapping.last_synced_at = timezone.now()
    mapping.save(update_fields=['notion_last_edited_ko', 'notion_last_edited_en', 'last_synced_at'])

    return stats


# ──────────────────────────────────────────────
# 6. HTML → Markdown 역변환
# ──────────────────────────────────────────────

def _html_to_md_inline(html: str) -> str:
    """인라인 HTML 태그를 마크다운으로 역변환"""
    # HTML 엔티티
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    # <strong> → **
    html = re.sub(r'<strong>(.*?)</strong>', r'**\1**', html)
    # <code> (인라인) → `
    html = re.sub(r'<code>(.*?)</code>', r'`\1`', html)
    # <a href="url">text</a> → [text](url)
    html = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', html)
    # <br> → 줄바꿈
    html = re.sub(r'<br\s*/?>', '\n', html)
    # 나머지 HTML 태그 제거
    html = re.sub(r'<[^>]+>', '', html)
    return html


def _html_to_plain_inline(html: str) -> str:
    """인라인 HTML 태그를 plain text로 변환 (코드블록 내부용)"""
    # HTML 엔티티
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    # <a> 태그에서 텍스트만 추출
    html = re.sub(r'<a\s+href="[^"]*"[^>]*>(.*?)</a>', r'\1', html)
    # <br> → 줄바꿈
    html = re.sub(r'<br\s*/?>', '\n', html)
    # 모든 HTML 태그 제거
    html = re.sub(r'<[^>]+>', '', html)
    return html


def _html_to_md_bullets(html: str, indent: int = 0, plain: bool = False) -> str:
    """<ul><li> 구조를 마크다운 bullet 리스트로 역변환 (plain=True면 코드블록용 plain text)"""
    if not html or not html.strip():
        return ''

    _inline_fn = _html_to_plain_inline if plain else _html_to_md_inline
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
                text_md = _inline_fn(text_part)
                md_lines = text_md.split('\n')
                lines.append(f'{prefix}- {md_lines[0]}')
                for cont in md_lines[1:]:
                    lines.append(f'{prefix}  {cont}')
                lines.append(f'{prefix}  ```')
                for code_line in code.strip().split('\n'):
                    lines.append(f'{prefix}  {code_line}')
                lines.append(f'{prefix}  ```')
                if sub_html:
                    lines.append(_html_to_md_bullets(sub_html, indent + 1, plain=plain))
                break
        else:
            text_md = _inline_fn(text_part)
            if text_md.strip():
                # <br> 줄바꿈 시 continuation line을 bullet 들여쓰기에 맞춤
                md_lines = text_md.split('\n')
                lines.append(f'{prefix}- {md_lines[0]}')
                for cont in md_lines[1:]:
                    lines.append(f'{prefix}  {cont}')
            if sub_html:
                lines.append(_html_to_md_bullets(sub_html, indent + 1, plain=plain))

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


def _build_patch_md(patch_note: PatchNote, lang: str = 'ko') -> str:
    """PatchNote 인스턴스를 Notion 원본 MD 형식으로 변환 (push용)"""
    is_en = lang == 'en'

    def _get_content(manager, plain=False):
        obj = manager.filter(parent__isnull=True).order_by('order', 'id').first()
        if not obj:
            return '- N/A'
        content = (obj.content_en if is_en and obj.content_en else obj.content) or ''
        if not content.strip():
            return '- N/A'
        return _html_to_md_bullets(content, plain=plain) or '- N/A'

    features_md = _get_content(patch_note.features, plain=True)
    improvements_md = _get_content(patch_note.improvements, plain=True)
    bugfixes_md = _get_content(patch_note.bugfixes, plain=True)
    remarks_md = _get_content(patch_note.remarks)

    remarks_tabbed = '\n'.join(
        '\t\t' + line if line.strip() else line
        for line in remarks_md.split('\n')
    )

    if is_en:
        cat_new, cat_imp, cat_bug = 'Added Features', 'Improved Features', 'Bug Fixes'
    else:
        cat_new, cat_imp, cat_bug = '기능 추가', '기능 개선', '버그 수정'

    lines = [
        f'\t\t## <span color="green_bg">{patch_note.version} </span>',
        f'\t\tDATE : {patch_note.release_date}',
        '\t\t**\\[*Patch notes*\\]**',
        '\t\t```plain text',
        cat_new,
        features_md,
        '',
        cat_imp,
        improvements_md,
        '',
        cat_bug,
        bugfixes_md,
        '\t\t```',
        '\t\t**\\[*Remarks*\\]**',
        remarks_tabbed,
        '\t\t<empty-block/>',
        '\t\t---',
    ]
    return '\n'.join(lines)


def patch_note_to_md(patch_note: PatchNote) -> str:
    """한국어 MD 변환 (하위 호환)"""
    return _build_patch_md(patch_note, lang='ko')


# ──────────────────────────────────────────────
# 7. Notion에 패치노트 Push
# ──────────────────────────────────────────────

def _notion_update_markdown(page_id: str, payload: dict):
    """Notion Markdown API에 PATCH 요청"""
    url = f'https://api.notion.com/v1/pages/{page_id}/markdown'
    res = requests.patch(url, headers=_get_notion_headers(), json=payload, timeout=30)
    res.raise_for_status()
    return res.json()


def _find_supported_anchor(md: str) -> str | None:
    """Notion 페이지에서 '지원중인 버전' 또는 'Supported Versions' 앵커를 찾아 반환"""
    match = re.search(r'^[ \t]*(#\s+\*{0,2}(?:지원\s*중인\s*버전|Supported\s+[Vv]ersions?)\*{0,2})', md, re.MULTILINE)
    return match.group(1) if match else None


def _push_to_page(page_id: str, md_content: str, is_new: bool, version: str):
    """단일 Notion 페이지에 패치노트 push"""
    current_md = fetch_page_markdown(page_id)
    

    if is_new:
        anchor = _find_supported_anchor(current_md)
        if not anchor:
            raise ValueError(f'Notion 페이지에서 지원 버전 앵커를 찾을 수 없습니다. (page_id={page_id})')
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
        pattern = re.compile(
            rf'(\t*##\s+(?:<span[^>]*>)?{re.escape(version)}\s*(?:</span>)?[\s\S]*?)(---\s*\n|(?=\t*##\s)|$)'
        )
        match = pattern.search(current_md)
        if not match:
            raise ValueError(f'Notion 페이지에서 버전 {version}을 찾을 수 없습니다. (page_id={page_id})')

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

    return _notion_update_markdown(page_id, payload)


def push_patch_note_to_notion(patch_note: PatchNote, is_new: bool = True) -> dict:
    """
    패치노트를 Notion 페이지에 push한다 (한국어 + 영문).

    Args:
        patch_note: PatchNote 인스턴스
        is_new: True면 insert_content, False면 update_content (기존 버전 수정)

    Returns:
        Notion API 응답 (한국어 페이지)
    """
    if not settings.NOTION_ENABLED or not settings.NOTION_TOKEN:
        raise ValueError('Notion 연동이 비활성화되어 있습니다.')

    try:
        mapping = NotionPageMapping.objects.get(product=patch_note.product)
    except NotionPageMapping.DoesNotExist:
        raise ValueError('해당 제품의 Notion 매핑 정보가 없습니다.')

    version = patch_note.version
    push_result = {'ko': None, 'en': None, 'en_status': 'skipped', 'en_reason': ''}

    # ── 한국어 페이지 push ──
    md_ko = _build_patch_md(patch_note, lang='ko')
    push_result['ko'] = _push_to_page(mapping.page_id_ko, md_ko, is_new, version)
    logger.info('Notion push 완료 (KO): %s v%s (%s)', patch_note.product, version, 'insert' if is_new else 'update')

    # ── 영문 페이지 push (매핑이 있고, 영문 콘텐츠가 있을 때) ──
    if not mapping.page_id_en:
        push_result['en_reason'] = 'page_id_en 미설정'
        logger.info('Notion 영문 push 건너뜀 — page_id_en 미설정 (%s)', patch_note.product)
    else:
        has_en = any(
            manager.filter(parent__isnull=True, content_en__isnull=False).exclude(content_en='').exists()
            for manager in [patch_note.features, patch_note.improvements, patch_note.bugfixes, patch_note.remarks]
        )
        if not has_en:
            push_result['en_reason'] = '영문 콘텐츠 없음 (content_en이 비어있음)'
            logger.info('Notion 영문 push 건너뜀 — 영문 콘텐츠 없음 (%s v%s)', patch_note.product, version)
        else:
            try:
                md_en = _build_patch_md(patch_note, lang='en')
                push_result['en'] = _push_to_page(mapping.page_id_en, md_en, is_new, version)
                push_result['en_status'] = 'success'
                logger.info('Notion push 완료 (EN): %s v%s (%s)', patch_note.product, version, 'insert' if is_new else 'update')
            except Exception as e:
                push_result['en_status'] = 'failed'
                push_result['en_reason'] = str(e)
                logger.error('Notion 영문 push 실패 (%s v%s): %s', patch_note.product, version, e, exc_info=True)

    return push_result


def push_en_to_notion(patch_note: PatchNote, is_new: bool = True) -> dict:
    """번역 완료 후 영문 페이지만 push (KO는 건드리지 않음)"""
    if not settings.NOTION_ENABLED or not settings.NOTION_TOKEN:
        raise ValueError('Notion 연동이 비활성화되어 있습니다.')

    try:
        mapping = NotionPageMapping.objects.get(product=patch_note.product)
    except NotionPageMapping.DoesNotExist:
        raise ValueError('해당 제품의 Notion 매핑 정보가 없습니다.')

    if not mapping.page_id_en:
        return {'en_status': 'skipped', 'en_reason': 'page_id_en 미설정'}

    version = patch_note.version
    has_en = any(
        manager.filter(parent__isnull=True, content_en__isnull=False).exclude(content_en='').exists()
        for manager in [patch_note.features, patch_note.improvements, patch_note.bugfixes, patch_note.remarks]
    )
    if not has_en:
        return {'en_status': 'skipped', 'en_reason': '영문 콘텐츠 없음'}

    md_en = _build_patch_md(patch_note, lang='en')
    _push_to_page(mapping.page_id_en, md_en, is_new, version)
    logger.info('Notion EN push 완료: %s v%s (%s)', patch_note.product, version, 'insert' if is_new else 'update')
    return {'en_status': 'success'}

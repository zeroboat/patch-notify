"""
Notion에서 변환된 JSON 패치노트를 DB에 일괄 import하는 management command

사용법:
  python manage.py import_patchnotes --base-dir /path/to/PATCH_NOTES_HTML

JSON 파일 구조:
  PATCH_NOTES_HTML/
  └── {Solution}/
      ├── {Platform}_{Category}.json       ← 한국어
      └── {Platform}_{Category}_en.json   ← 영어 (없을 수 있음)
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.patchnote.models import BugFix, Feature, Improvement, PatchNote, Remark
from apps.product.models import Product, Solution

PLATFORM_MAP = {
    'android': 'AOS',
    'ios':     'IOS',
    'server':  'SERVER',
    'macos':   'MACOS',
    'web':     'WEB',
    'flutter': 'FLUTTER',
}

CATEGORY_MAP = {
    'library':  'LIB',
    'plugin':   'PLG',
    'backend':  'BND',
    'frontend': 'FND',
    'module':   'MOD',
}


def _convert_markdown(html: str) -> str:
    """HTML 내부의 인라인 마크다운 패턴을 HTML 태그로 변환"""
    # ```lang code ``` → <code>code</code>
    html = re.sub(
        r'```(?:\w+)?\s*([\s\S]*?)```',
        lambda m: '<code>' + m.group(1).strip() + '</code>',
        html,
    )
    # **text** → <strong>text</strong>
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    return html


def _clean_html(html: str) -> str:
    """마크다운 변환 → 빈 <p> 제거 → <p> 태그 strip"""
    html = (html or '').strip()
    if not html:
        return ''
    html = _convert_markdown(html)
    html = re.sub(r'<p(?=\s|>)[^>]*>(\s|&nbsp;|<br\s*/?>)*</p>', '', html)
    html = re.sub(r'<p(?=\s|>)(?:\s[^>]*)?>',  '', html)
    html = re.sub(r'</p>', '', html)
    html = html.strip()
    text_only = re.sub(r'<[^>]+>', '', html).replace('\xa0', '').replace('&nbsp;', '').strip()
    return html if text_only else ''


def _save_section(patch_note, html_ko, html_en, model_class):
    html_ko = _clean_html(html_ko)
    html_en = _clean_html(html_en)
    if not html_ko and not html_en:
        return
    model_class.objects.create(
        patch_note=patch_note,
        content=html_ko or '',
        content_en=html_en or None,
        order=0,
    )


def _parse_filename(stem: str):
    """
    'Android_Library' → ('AOS', 'LIB')
    반환값이 None이면 매핑 실패
    """
    parts = stem.split('_', 1)
    if len(parts) != 2:
        return None, None
    platform = PLATFORM_MAP.get(parts[0].lower())
    category = CATEGORY_MAP.get(parts[1].lower())
    return platform, category


class Command(BaseCommand):
    help = 'PATCH_NOTES_HTML 디렉토리의 JSON 파일을 DB에 일괄 import합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-dir',
            required=True,
            help='PATCH_NOTES_HTML 디렉토리 경로',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='실제 저장 없이 처리 결과만 출력',
        )

    def handle(self, *args, **options):
        base_dir = Path(options['base_dir'])
        dry_run  = options['dry_run']

        if not base_dir.exists():
            raise CommandError(f'디렉토리를 찾을 수 없습니다: {base_dir}')

        stats = {'created': 0, 'skipped': 0, 'error': 0}

        # 한국어 JSON 파일만 순회 (_en.json 제외)
        ko_files = sorted(base_dir.rglob('*.json'))
        ko_files = [f for f in ko_files if not f.stem.endswith('_en')]

        for ko_path in ko_files:
            solution_name = ko_path.parent.name
            platform, category = _parse_filename(ko_path.stem)

            if not platform or not category:
                self.stderr.write(f'  [SKIP] 파일명 파싱 실패: {ko_path.name}')
                stats['error'] += 1
                continue

            # 영문 파일 경로
            en_path = ko_path.with_stem(ko_path.stem + '_en')

            try:
                ko_data = json.loads(ko_path.read_text(encoding='utf-8'))
            except Exception as e:
                self.stderr.write(f'  [ERROR] {ko_path}: {e}')
                stats['error'] += 1
                continue

            en_notes_by_version = {}
            if en_path.exists():
                try:
                    en_data = json.loads(en_path.read_text(encoding='utf-8'))
                    en_notes_by_version = {
                        n['version']: n for n in en_data.get('patch_notes', [])
                    }
                except Exception as e:
                    self.stderr.write(f'  [WARN] 영문 파일 로드 실패 {en_path.name}: {e}')

            self.stdout.write(f'\n▶ {solution_name} / {ko_path.stem}')

            if not dry_run:
                solution, _ = Solution.objects.get_or_create(name=solution_name)
                product, _ = Product.objects.get_or_create(
                    solution=solution,
                    platform=platform,
                    category=category,
                )

            for note_data in ko_data.get('patch_notes', []):
                version    = note_data.get('version', '').strip()
                patch_date = note_data.get('patch_date', '').strip()

                if not version or not patch_date:
                    self.stderr.write(f'    [SKIP] version/date 없음')
                    stats['skipped'] += 1
                    continue

                en = en_notes_by_version.get(version, {})

                if dry_run:
                    self.stdout.write(f'    v{version} ({patch_date}) → dry-run')
                    stats['created'] += 1
                    continue

                patch_note, created = PatchNote.objects.get_or_create(
                    product=product,
                    version=version,
                    defaults={'release_date': patch_date},
                )

                if not created:
                    self.stdout.write(f'    v{version} → 이미 존재, skip')
                    stats['skipped'] += 1
                    continue

                _save_section(patch_note, note_data.get('new_features'), en.get('new_features'), Feature)
                _save_section(patch_note, note_data.get('improvements'), en.get('improvements'), Improvement)
                _save_section(patch_note, note_data.get('bug_fixes'),    en.get('bug_fixes'),    BugFix)
                _save_section(patch_note, note_data.get('special_notes'),en.get('special_notes'),Remark)

                self.stdout.write(f'    v{version} ({patch_date}) → 등록 완료')
                stats['created'] += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 등록: {stats["created"]}, skip: {stats["skipped"]}, 오류: {stats["error"]}'
        ))

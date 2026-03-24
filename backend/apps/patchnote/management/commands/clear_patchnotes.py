"""
패치노트 전체 데이터를 삭제하는 management command

사용법:
  python manage.py clear_patchnotes              # 확인 프롬프트 후 삭제
  python manage.py clear_patchnotes --yes        # 확인 없이 즉시 삭제
  python manage.py clear_patchnotes --product 3  # 특정 Product ID만 삭제
"""

from django.core.management.base import BaseCommand

from apps.patchnote.models import PatchNote


class Command(BaseCommand):
    help = '패치노트 데이터를 일괄 삭제합니다. (연관 섹션 포함 CASCADE)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='확인 프롬프트 없이 즉시 삭제',
        )
        parser.add_argument(
            '--product',
            type=int,
            metavar='PRODUCT_ID',
            help='특정 Product ID의 패치노트만 삭제',
        )

    def handle(self, *args, **options):
        qs = PatchNote.objects.all()

        if options['product']:
            qs = qs.filter(product_id=options['product'])
            scope = f'Product ID={options["product"]}'
        else:
            scope = '전체'

        count = qs.count()
        if count == 0:
            self.stdout.write('삭제할 패치노트가 없습니다.')
            return

        self.stdout.write(f'삭제 대상: {scope} 패치노트 {count}건 (연관 섹션 포함)')

        if not options['yes']:
            confirm = input('정말 삭제하시겠습니까? [y/N] ').strip().lower()
            if confirm != 'y':
                self.stdout.write('취소되었습니다.')
                return

        qs.delete()
        self.stdout.write(self.style.SUCCESS(f'{count}건 삭제 완료'))

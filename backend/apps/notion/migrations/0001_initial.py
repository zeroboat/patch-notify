import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('product', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotionPageMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성일시')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='수정일시')),
                ('page_id_ko', models.CharField(max_length=100, verbose_name='한국어 페이지 ID')),
                ('page_id_en', models.CharField(blank=True, default='', max_length=100, verbose_name='영문 페이지 ID')),
                ('product', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notion_mapping',
                    to='product.product',
                    verbose_name='제품',
                )),
            ],
            options={
                'verbose_name': 'Notion 페이지 매핑',
                'verbose_name_plural': 'Notion 페이지 매핑 목록',
            },
        ),
    ]

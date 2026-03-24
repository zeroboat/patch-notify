from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notion', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notionpagemapping',
            name='notion_last_edited_ko',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Notion 한국어 최종 수정일'),
        ),
        migrations.AddField(
            model_name='notionpagemapping',
            name='notion_last_edited_en',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Notion 영문 최종 수정일'),
        ),
        migrations.AddField(
            model_name='notionpagemapping',
            name='last_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='마지막 동기화 일시'),
        ),
    ]

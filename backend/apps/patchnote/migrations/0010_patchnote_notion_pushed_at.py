from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patchnote', '0009_patchnote_external_send_error_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patchnote',
            name='notion_pushed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Notion Push 일시'),
        ),
    ]

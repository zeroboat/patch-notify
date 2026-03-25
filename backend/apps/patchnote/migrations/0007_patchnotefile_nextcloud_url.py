from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patchnote', '0006_patchnotefile'),
    ]

    operations = [
        migrations.AddField(
            model_name='patchnotefile',
            name='nextcloud_url',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='Nextcloud 다운로드 URL'),
        ),
    ]

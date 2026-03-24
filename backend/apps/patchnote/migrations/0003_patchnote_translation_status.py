from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patchnote', '0002_bugfix_content_en_feature_content_en_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='patchnote',
            name='translation_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('translating', 'Translating'),
                    ('done', 'Done'),
                    ('failed', 'Failed'),
                    ('skipped', 'Skipped'),
                ],
                default='skipped',
                max_length=15,
                verbose_name='번역 상태',
            ),
        ),
    ]

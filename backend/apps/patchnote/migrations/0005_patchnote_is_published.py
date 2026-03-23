from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patchnote', '0004_set_existing_translation_done'),
    ]

    operations = [
        migrations.AddField(
            model_name='patchnote',
            name='is_published',
            field=models.BooleanField(default=False, verbose_name='발행 여부'),
        ),
    ]

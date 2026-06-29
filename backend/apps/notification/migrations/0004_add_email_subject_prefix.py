from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0003_add_patchnote_title_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='noticeconfig',
            name='email_subject_prefix',
            field=models.CharField(default='Patch Notify', max_length=100, verbose_name='이메일 제목 접두사'),
        ),
    ]

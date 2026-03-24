import apps.patchnote.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('patchnote', '0005_patchnote_is_published'),
    ]

    operations = [
        migrations.CreateModel(
            name='PatchNoteFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성일시')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='수정일시')),
                ('file_type', models.CharField(choices=[('release', 'Release'), ('debug', 'Debug')], max_length=10, verbose_name='파일 유형')),
                ('file', models.FileField(upload_to=apps.patchnote.models.patchnote_file_upload_path, verbose_name='파일')),
                ('original_filename', models.CharField(max_length=255, verbose_name='원본 파일명')),
                ('file_size', models.PositiveBigIntegerField(default=0, verbose_name='파일 크기(bytes)')),
                ('patch_note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='files', to='patchnote.patchnote', verbose_name='패치노트')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_patchnote_files', to=settings.AUTH_USER_MODEL, verbose_name='업로더')),
            ],
            options={
                'verbose_name': '패치노트 파일',
                'verbose_name_plural': '패치노트 파일 목록',
                'ordering': ['file_type', '-created_at'],
            },
        ),
    ]

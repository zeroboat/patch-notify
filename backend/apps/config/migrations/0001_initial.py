from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SiteConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gmail_user', models.EmailField(blank=True, verbose_name='Gmail 계정')),
                ('gmail_app_password', models.CharField(blank=True, max_length=200, verbose_name='Gmail 앱 비밀번호')),
                ('ollama_host', models.CharField(blank=True, max_length=200, verbose_name='Ollama 서버 주소')),
                ('ollama_model', models.CharField(blank=True, max_length=100, verbose_name='Ollama 모델명')),
                ('notion_enabled', models.BooleanField(default=False, verbose_name='Notion 연동 활성화')),
                ('notion_token', models.CharField(blank=True, max_length=500, verbose_name='Notion API 토큰')),
                ('nextcloud_enabled', models.BooleanField(default=False, verbose_name='Nextcloud 연동 활성화')),
                ('nextcloud_url', models.CharField(blank=True, max_length=200, verbose_name='Nextcloud 서버 URL')),
                ('nextcloud_user', models.CharField(blank=True, max_length=100, verbose_name='Nextcloud 계정')),
                ('nextcloud_password', models.CharField(blank=True, max_length=200, verbose_name='Nextcloud 비밀번호')),
                ('nextcloud_upload_path', models.CharField(default='/patch-notify/media', max_length=200, verbose_name='Nextcloud 업로드 경로')),
            ],
            options={
                'verbose_name': '서비스 설정',
                'verbose_name_plural': '서비스 설정',
            },
        ),
    ]

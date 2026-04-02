from django.contrib import admin
from .models import SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Gmail SMTP', {
            'fields': ('gmail_user', 'gmail_app_password'),
            'description': 'Google 계정 > 보안 > 앱 비밀번호에서 발급한 값을 입력하세요.',
        }),
        ('Ollama AI 번역', {
            'fields': ('ollama_host', 'ollama_model'),
            'description': '내부 Ollama 서버 주소와 사용할 모델명을 입력하세요. (예: http://192.168.0.10:11434)',
        }),
        ('Notion 연동', {
            'fields': ('notion_enabled', 'notion_token'),
            'description': 'https://www.notion.so/my-integrations 에서 Integration 생성 후 토큰을 입력하세요.',
        }),
        ('Nextcloud (NAS 이중 저장)', {
            'fields': ('nextcloud_enabled', 'nextcloud_url', 'nextcloud_user', 'nextcloud_password', 'nextcloud_upload_path'),
            'description': 'Nextcloud 앱 비밀번호 사용을 권장합니다. (설정 > 보안 > 앱 비밀번호)',
        }),
    )

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

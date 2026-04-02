from django.db import models
from django.core.cache import cache

CACHE_KEY = 'site_config'
CACHE_TTL = 300  # 5분


class SiteConfig(models.Model):
    """서비스 설정 싱글톤 모델 — Admin에서 관리, DB에 저장"""

    # Gmail
    gmail_user = models.EmailField(blank=True, verbose_name='Gmail 계정')
    gmail_app_password = models.CharField(max_length=200, blank=True, verbose_name='Gmail 앱 비밀번호')

    # Ollama
    ollama_host = models.CharField(max_length=200, blank=True, verbose_name='Ollama 서버 주소')
    ollama_model = models.CharField(max_length=100, blank=True, verbose_name='Ollama 모델명')

    # Notion
    notion_enabled = models.BooleanField(default=False, verbose_name='Notion 연동 활성화')
    notion_token = models.CharField(max_length=500, blank=True, verbose_name='Notion API 토큰')

    # Nextcloud
    nextcloud_enabled = models.BooleanField(default=False, verbose_name='Nextcloud 연동 활성화')
    nextcloud_url = models.CharField(max_length=200, blank=True, verbose_name='Nextcloud 서버 URL')
    nextcloud_user = models.CharField(max_length=100, blank=True, verbose_name='Nextcloud 계정')
    nextcloud_password = models.CharField(max_length=200, blank=True, verbose_name='Nextcloud 비밀번호')
    nextcloud_upload_path = models.CharField(
        max_length=200, default='/patch-notify/media', verbose_name='Nextcloud 업로드 경로'
    )

    class Meta:
        verbose_name = '서비스 설정'
        verbose_name_plural = '서비스 설정'

    def __str__(self):
        return '서비스 설정'

    def save(self, *args, **kwargs):
        self.pk = 1  # 항상 pk=1 유지 (싱글톤)
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass  # 삭제 방지

    @classmethod
    def get(cls):
        """캐시 우선 조회. 없으면 DB에서 가져오거나 기본값으로 생성."""
        config = cache.get(CACHE_KEY)
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, config, CACHE_TTL)
        return config

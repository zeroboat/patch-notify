from django.db import models
from django.core.cache import cache
from apps.base.models import BaseModel

_NOTICE_CONFIG_CACHE_KEY = 'notice_config'
_NOTICE_CONFIG_CACHE_TTL = 300

_DEFAULT_FOOTER_TEXT = (
    '이 메일은 Patch Notify 시스템에서 자동 발송되었습니다.\n'
    '문의사항이 있으시면 담당자에게 연락해 주세요.'
)

_DEFAULT_PATCHNOTE_TITLE_FORMAT = '{product} Release 안내'


class NoticeConfig(models.Model):
    """공문 이메일 템플릿 설정 싱글톤"""

    upper_logo = models.ImageField(upload_to='notice_logos/', null=True, blank=True, verbose_name='상단 로고')
    upper_logo_width = models.PositiveIntegerField(default=120, verbose_name='상단 로고 너비 (px)')
    lower_logo = models.ImageField(upload_to='notice_logos/', null=True, blank=True, verbose_name='하단 로고')
    lower_logo_width = models.PositiveIntegerField(default=200, verbose_name='하단 로고 너비 (px)')
    header_color = models.CharField(max_length=20, default='#501A9B', verbose_name='헤더 색상')
    footer_text = models.TextField(default=_DEFAULT_FOOTER_TEXT, verbose_name='하단 문구')
    patchnote_title_format = models.CharField(
        max_length=200,
        default=_DEFAULT_PATCHNOTE_TITLE_FORMAT,
        verbose_name='패치노트 이메일 제목 형식',
    )

    class Meta:
        verbose_name = '공문 템플릿 설정'
        verbose_name_plural = '공문 템플릿 설정'

    def __str__(self):
        return '공문 템플릿 설정'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(_NOTICE_CONFIG_CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get(cls):
        cfg = cache.get(_NOTICE_CONFIG_CACHE_KEY)
        if cfg is None:
            cfg, _ = cls.objects.get_or_create(pk=1)
            cache.set(_NOTICE_CONFIG_CACHE_KEY, cfg, _NOTICE_CONFIG_CACHE_TTL)
        return cfg


class OfficialNotice(BaseModel):
    SEND_MODE_CHOICES = [
        ('direct', '직접 입력'),
        ('solution', '솔루션 선택'),
    ]

    subject = models.CharField(max_length=300, verbose_name="제목")
    body = models.TextField(verbose_name="본문")
    send_mode = models.CharField(max_length=10, choices=SEND_MODE_CHOICES, verbose_name="발송 방식")
    recipients_json = models.TextField(blank=True, default='[]', verbose_name="수신자 목록(JSON)")
    recipient_count = models.PositiveIntegerField(default=0, verbose_name="수신자 수")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="발송일시")

    class Meta:
        verbose_name = "공문"
        verbose_name_plural = "공문 목록"
        ordering = ['-created_at']

    def __str__(self):
        return self.subject

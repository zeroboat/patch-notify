from django.db import models
from apps.base.models import BaseModel


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

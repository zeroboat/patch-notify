from django.db import models
from apps.base.models import BaseModel


class DispatchLog(BaseModel):
    TYPE_OFFICIAL = 'official'
    TYPE_SUBSCRIPTION = 'subscription'
    LOG_TYPE_CHOICES = [
        (TYPE_OFFICIAL, '공문'),
        (TYPE_SUBSCRIPTION, '구독 자동발송'),
    ]

    CHANNEL_EMAIL = 'email'
    CHANNEL_SLACK = 'slack'
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, 'Gmail'),
        (CHANNEL_SLACK, 'Slack'),
    ]

    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PENDING = 'pending'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, '성공'),
        (STATUS_FAILED, '실패'),
        (STATUS_PENDING, '대기'),
    ]

    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, verbose_name="발송 유형")
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, verbose_name="채널")
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_logs',
        verbose_name="고객사",
    )
    solution = models.ForeignKey(
        'product.Solution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_logs',
        verbose_name="솔루션",
    )
    official_notice = models.ForeignKey(
        'notification.OfficialNotice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_logs',
        verbose_name="공문",
    )
    recipient = models.TextField(verbose_name="수신자")
    subject = models.CharField(max_length=300, blank=True, verbose_name="제목")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="상태")
    error_message = models.TextField(blank=True, verbose_name="오류 메시지")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="발송일시")

    class Meta:
        verbose_name = "발송 로그"
        verbose_name_plural = "발송 로그 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_log_type_display()}] {self.recipient} · {self.get_status_display()}"

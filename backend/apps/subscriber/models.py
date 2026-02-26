from django.db import models
from apps.base.models import BaseModel


class Subscription(BaseModel):
    CHANNEL_EMAIL = 'email'
    CHANNEL_SLACK = 'slack'
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, 'Gmail'),
        (CHANNEL_SLACK, 'Slack'),
    ]

    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_MONTHLY = 'monthly'
    FREQUENCY_QUARTERLY = 'quarterly'
    FREQUENCY_CHOICES = [
        (FREQUENCY_WEEKLY, '매주'),
        (FREQUENCY_MONTHLY, '매월'),
        (FREQUENCY_QUARTERLY, '분기'),
    ]

    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name="고객사",
    )
    solution = models.ForeignKey(
        'product.Solution',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name="솔루션",
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, verbose_name="채널")
    is_active = models.BooleanField(default=True, verbose_name="활성화")
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default=FREQUENCY_WEEKLY,
        verbose_name="전달 주기",
    )
    max_items = models.PositiveIntegerField(default=5, verbose_name="최대 건수")
    slack_channel = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Slack 채널",
        help_text="Slack 채널명 (예: #patch-notes)",
    )

    class Meta:
        verbose_name = "구독"
        verbose_name_plural = "구독 목록"
        unique_together = ['customer', 'solution', 'channel']
        ordering = ['customer__name', 'solution__name', 'channel']

    def __str__(self):
        return f"{self.customer.name} · {self.solution.name} · {self.get_channel_display()}"

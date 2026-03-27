from django.db import models
from apps.base.models import BaseModel


class Subscription(BaseModel):
    CHANNEL_EMAIL = 'email'
    CHANNEL_SLACK = 'slack'
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, 'Gmail'),
        (CHANNEL_SLACK, 'Slack'),
    ]

    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name="고객사",
    )
    product = models.ForeignKey(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name="제품",
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, verbose_name="채널")
    is_active = models.BooleanField(default=True, verbose_name="활성화")
    max_items = models.PositiveIntegerField(default=5, verbose_name="최대 건수")
    slack_channel = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Slack 채널",
        help_text="Slack 채널 ID",
    )

    class Meta:
        verbose_name = "구독"
        verbose_name_plural = "구독 목록"
        unique_together = ['customer', 'product', 'channel']
        ordering = ['customer__name', 'product__solution__name', 'channel']

    def __str__(self):
        return f"{self.customer.name} · {self.product} · {self.get_channel_display()}"

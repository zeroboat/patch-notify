from django.db import models
from apps.base.models import BaseModel


class SlackWorkspace(BaseModel):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        ('pending', '승인 대기'),
        ('approved', '승인됨'),
        ('rejected', '거부됨'),
    ]

    team_id = models.CharField(max_length=50, unique=True, verbose_name="팀 ID")
    team_name = models.CharField(max_length=200, verbose_name="워크스페이스명")
    bot_token = models.CharField(max_length=500, verbose_name="Bot Token")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="상태",
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='slack_workspaces',
        verbose_name="고객사",
    )
    is_internal = models.BooleanField(
        default=False,
        verbose_name="사내 워크스페이스",
        help_text="체크 시 사내 알림 발송에 사용됩니다. 1개만 활성화하세요.",
    )

    class Meta:
        verbose_name = "Slack 워크스페이스"
        verbose_name_plural = "Slack 워크스페이스 목록"

    def __str__(self):
        return f"{self.team_name} ({self.get_status_display()})"

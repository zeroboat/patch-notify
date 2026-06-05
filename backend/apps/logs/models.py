from django.db import models
from django.contrib.auth.models import User
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


class ActionLog(models.Model):
    """웹 페이지 액션 로그 — 사용자가 수행한 주요 작업 기록"""

    # 액션 코드 상수
    PATCHNOTE_CREATE  = 'patchnote_create'
    PATCHNOTE_UPDATE  = 'patchnote_update'
    PATCHNOTE_DELETE  = 'patchnote_delete'
    PATCHNOTE_PUBLISH = 'patchnote_publish'
    NOTION_SYNC       = 'notion_sync'
    NOTION_PUSH       = 'notion_push'
    CUSTOMER_CREATE   = 'customer_create'
    CUSTOMER_UPDATE   = 'customer_update'
    CUSTOMER_DELETE   = 'customer_delete'
    SUBSCRIPTION_CHANGE = 'subscription_change'
    SLACK_APPROVE     = 'slack_approve'
    SLACK_REJECT      = 'slack_reject'
    PRODUCT_CREATE    = 'product_create'
    PRODUCT_UPDATE    = 'product_update'
    PRODUCT_DELETE    = 'product_delete'
    SOLUTION_CREATE   = 'solution_create'
    SOLUTION_UPDATE   = 'solution_update'
    SOLUTION_DELETE   = 'solution_delete'
    UTILITY_CREATE    = 'utility_create'
    UTILITY_UPDATE    = 'utility_update'
    UTILITY_DELETE    = 'utility_delete'

    ACTION_LABELS = {
        PATCHNOTE_CREATE:   '패치노트 등록',
        PATCHNOTE_UPDATE:   '패치노트 수정',
        PATCHNOTE_DELETE:   '패치노트 삭제',
        PATCHNOTE_PUBLISH:  '패치노트 발행',
        NOTION_SYNC:        'Notion 동기화',
        NOTION_PUSH:        'Notion Push',
        CUSTOMER_CREATE:    '고객사 등록',
        CUSTOMER_UPDATE:    '고객사 수정',
        CUSTOMER_DELETE:    '고객사 삭제',
        SUBSCRIPTION_CHANGE:'구독 설정 변경',
        SLACK_APPROVE:      'Slack 워크스페이스 승인',
        SLACK_REJECT:       'Slack 워크스페이스 거부',
        SOLUTION_CREATE:    '솔루션 등록',
        SOLUTION_UPDATE:    '솔루션 수정',
        SOLUTION_DELETE:    '솔루션 삭제',
        PRODUCT_CREATE:     '제품 등록',
        PRODUCT_UPDATE:     '제품 수정',
        PRODUCT_DELETE:     '제품 삭제',
        UTILITY_CREATE:     '유틸리티 등록',
        UTILITY_UPDATE:     '유틸리티 수정',
        UTILITY_DELETE:     '유틸리티 삭제',
    }

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='action_logs', verbose_name='수행자',
    )
    action = models.CharField(max_length=50, verbose_name='액션 코드')
    target = models.CharField(max_length=300, verbose_name='대상')
    detail = models.JSONField(null=True, blank=True, verbose_name='상세 정보')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='일시')

    class Meta:
        verbose_name = '액션 로그'
        verbose_name_plural = '액션 로그 목록'
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.action_label}] {self.target}"

    @property
    def action_label(self):
        return self.ACTION_LABELS.get(self.action, self.action)

    @classmethod
    def record(cls, request, action, target, detail=None):
        """뷰에서 한 줄로 호출하는 헬퍼"""
        actor = request.user if request.user.is_authenticated else None
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
        try:
            cls.objects.create(actor=actor, action=action, target=str(target), detail=detail, ip_address=ip)
        except Exception:
            pass  # 로깅 실패가 실제 동작에 영향 주지 않도록

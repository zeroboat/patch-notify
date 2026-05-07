from django.db import models
from django.contrib.auth import get_user_model
from apps.base.models import BaseModel

User = get_user_model()


class Feedback(BaseModel):
    class Category(models.TextChoices):
        BUG = 'bug', '버그 / 오류'
        UX = 'ux', '사용성 개선'
        FEATURE = 'feature', '신규 기능 요청'
        QUESTION = 'question', '질문 / 사용 문의'
        OTHER = 'other', '기타'

    class Status(models.TextChoices):
        OPEN = 'open', '접수'
        REVIEWING = 'reviewing', '검토 중'
        PLANNED = 'planned', '반영 예정'
        IN_PROGRESS = 'in_progress', '진행 중'
        DONE = 'done', '반영 완료'
        WONT_DO = 'wont_do', '미반영'
        DUPLICATE = 'duplicate', '중복'

    class Priority(models.TextChoices):
        LOW = 'low', '낮음'
        MEDIUM = 'medium', '보통'
        HIGH = 'high', '높음'

    STATUS_OPEN = [Status.OPEN, Status.REVIEWING]

    title = models.CharField(max_length=200, verbose_name='제목')
    content = models.TextField(verbose_name='내용')
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.UX, verbose_name='분류'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name='상태'
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM, verbose_name='우선순위'
    )
    page_url = models.CharField(max_length=500, blank=True, verbose_name='발생 화면 URL')
    attachment = models.FileField(
        upload_to='feedback/%Y/%m/', blank=True, null=True, verbose_name='첨부 파일'
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='feedbacks', verbose_name='작성자'
    )
    author_name = models.CharField(max_length=100, blank=True, verbose_name='작성자 표시명')
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_feedbacks', verbose_name='담당자'
    )
    resolution_note = models.TextField(blank=True, verbose_name='처리 메모')
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = '피드백'
        verbose_name_plural = '피드백 목록'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status in (self.Status.OPEN, self.Status.REVIEWING)


class FeedbackComment(BaseModel):
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name='comments'
    )
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    author_name = models.CharField(max_length=100, blank=True, verbose_name='작성자 표시명')
    content = models.TextField(verbose_name='댓글')

    class Meta:
        verbose_name = '피드백 댓글'
        ordering = ['created_at']

    def __str__(self):
        return f'[{self.feedback.title}] {self.author}'

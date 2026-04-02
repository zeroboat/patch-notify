from django.db import models
from apps.base.models import BaseModel
class PatchNote(BaseModel):
    """패치노트 메인 모델"""
    TRANSLATION_PENDING     = 'pending'
    TRANSLATION_TRANSLATING = 'translating'
    TRANSLATION_DONE        = 'done'
    TRANSLATION_FAILED      = 'failed'
    TRANSLATION_SKIPPED     = 'skipped'
    TRANSLATION_STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('translating', 'Translating'),
        ('done',        'Done'),
        ('failed',      'Failed'),
        ('skipped',     'Skipped'),
    ]

    product = models.ForeignKey('product.Product', on_delete=models.CASCADE, related_name='patch_notes', verbose_name="제품")
    version = models.CharField(max_length=30, verbose_name="버전")
    release_date = models.DateField(verbose_name="배포일")
    translation_status = models.CharField(
        max_length=15,
        choices=TRANSLATION_STATUS_CHOICES,
        default='skipped',
        verbose_name="번역 상태",
    )
    is_published = models.BooleanField(default=False, verbose_name="발행 여부")

    class Meta:
        verbose_name = "패치노트"
        verbose_name_plural = "패치노트 목록"
        unique_together = ['product', 'version']
        ordering = ['-release_date']

    def __str__(self):
        return f"{self.product} - {self.version}"

class PatchItemBase(BaseModel):
    """패치노트 공통 베이스 모델"""
    content = models.TextField(verbose_name="내용")
    content_en = models.TextField(verbose_name="내용(영문)", blank=True, null=True)
    order = models.PositiveIntegerField(default=0, verbose_name="순서")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name="상위 항목")

    class Meta:
        abstract = True
        ordering = ['order', 'id']

class Feature(PatchItemBase):
    """기능 추가"""
    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='features', verbose_name="기능 추가")
    class Meta(PatchItemBase.Meta): verbose_name = "기능 추가"

class Improvement(PatchItemBase):
    """기능 개선"""
    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='improvements', verbose_name="기능 개선")
    class Meta(PatchItemBase.Meta): verbose_name = "기능 개선"

class BugFix(PatchItemBase):
    """버그 수정"""
    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='bugfixes', verbose_name="버그 수정")
    class Meta(PatchItemBase.Meta): verbose_name = "버그 수정"

class Remark(PatchItemBase):
    """비고/특이사항"""
    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='remarks', verbose_name="특이사항")
    class Meta(PatchItemBase.Meta): verbose_name = "특이사항"

class Internal(PatchItemBase):
    """내부 공유 사항 (웹 페이지에서만 표시, 외부 공유 제외)"""
    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='internals', verbose_name="내부 공유")
    class Meta(PatchItemBase.Meta): verbose_name = "내부 공유"


def patchnote_file_upload_path(instance, filename):
    note = instance.patch_note
    solution = note.product.solution.name
    product = f"{note.product.get_platform_display()}_{note.product.get_category_display()}"
    version = note.version
    return f"patchnotes/{solution}/{product}/{version}/{instance.file_type}/{filename}"


class PatchNoteFile(BaseModel):
    """패치노트 첨부 파일 (릴리즈/디버그)"""
    FILE_TYPE_CHOICES = [
        ('release', 'Release'),
        ('debug', 'Debug'),
    ]

    patch_note = models.ForeignKey(PatchNote, on_delete=models.CASCADE, related_name='files', verbose_name="패치노트")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, verbose_name="파일 유형")
    file = models.FileField(upload_to=patchnote_file_upload_path, verbose_name="파일")
    original_filename = models.CharField(max_length=255, verbose_name="원본 파일명")
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="파일 크기(bytes)")
    nextcloud_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="Nextcloud 다운로드 URL")
    uploaded_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_patchnote_files', verbose_name="업로더"
    )

    class Meta:
        verbose_name = "패치노트 파일"
        verbose_name_plural = "패치노트 파일 목록"
        ordering = ['file_type', '-created_at']

    def __str__(self):
        return f"{self.patch_note} - {self.get_file_type_display()} - {self.original_filename}"

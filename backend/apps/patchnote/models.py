from django.db import models
from apps.base.models import BaseModel
class PatchNote(BaseModel):
    """패치노트 메인 모델"""
    product = models.ForeignKey('product.Product', on_delete=models.CASCADE, related_name='patch_notes', verbose_name="제품")
    version = models.CharField(max_length=30, verbose_name="버전")
    release_date = models.DateField(verbose_name="배포일")

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

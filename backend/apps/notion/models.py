from django.db import models
from apps.base.models import BaseModel


class NotionPageMapping(BaseModel):
    """Product 또는 Utility ↔ Notion 페이지 매핑"""
    product = models.OneToOneField(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='notion_mapping',
        verbose_name="제품",
        null=True, blank=True,
    )
    utility = models.OneToOneField(
        'product.Utility',
        on_delete=models.CASCADE,
        related_name='notion_mapping',
        verbose_name="유틸리티",
        null=True, blank=True,
    )
    page_id_ko = models.CharField(max_length=100, verbose_name="한국어 페이지 ID")
    page_id_en = models.CharField(max_length=100, verbose_name="영문 페이지 ID", blank=True, default='')
    notion_last_edited_ko = models.DateTimeField(null=True, blank=True, verbose_name="Notion 한국어 최종 수정일")
    notion_last_edited_en = models.DateTimeField(null=True, blank=True, verbose_name="Notion 영문 최종 수정일")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="마지막 동기화 일시")

    class Meta:
        verbose_name = "Notion 페이지 매핑"
        verbose_name_plural = "Notion 페이지 매핑 목록"

    def __str__(self):
        subject = self.product or self.utility
        return f"{subject} → {self.page_id_ko[:12]}..."

    @property
    def subject(self):
        return self.product if self.product_id else self.utility

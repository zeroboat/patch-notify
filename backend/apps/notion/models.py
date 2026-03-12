from django.db import models
from apps.base.models import BaseModel


class NotionPageMapping(BaseModel):
    """Product ↔ Notion 페이지 매핑"""
    product = models.OneToOneField(
        'product.Product',
        on_delete=models.CASCADE,
        related_name='notion_mapping',
        verbose_name="제품",
    )
    page_id_ko = models.CharField(max_length=100, verbose_name="한국어 페이지 ID")
    page_id_en = models.CharField(max_length=100, verbose_name="영문 페이지 ID", blank=True, default='')

    class Meta:
        verbose_name = "Notion 페이지 매핑"
        verbose_name_plural = "Notion 페이지 매핑 목록"

    def __str__(self):
        return f"{self.product} → {self.page_id_ko[:12]}..."

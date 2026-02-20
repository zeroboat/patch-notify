from django.db import models

from apps.base.models import BaseModel

# Create your models here.

class Solution(BaseModel):
    name = models.CharField(max_length=100, verbose_name="솔루션 명")
    icon = models.CharField(max_length=50, verbose_name="아이콘", null=True, blank=True)

    class Meta:
        verbose_name = "솔루션"
        verbose_name_plural = "솔루션 목록"

    def __str__(self):
        return self.name
    
class Product(BaseModel):
    class Platform(models.TextChoices):
        AOS = 'AOS', 'Android'
        IOS = 'IOS', 'iOS'
        SERVER = 'SERVER', 'Server'
        MACOS = 'MACOS', 'macOS'
        WEB = 'WEB', 'Web'
        FLUTTER = 'FLUTTER', 'Flutter'
    class Category(models.TextChoices):
        LIBRARY = 'LIB', 'Library'
        PLUGIN = 'PLG', 'Plugin'
        BACKEND = 'BND', 'Backend'
        FRONTEND = 'FND', 'Frontend'
        MODULE = 'MOD', 'Module'
    solution = models.ForeignKey(Solution, on_delete=models.CASCADE, related_name='products', verbose_name="소속 솔루션")
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.AOS, verbose_name="플랫폼")
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.PLUGIN, verbose_name="카테고리")
    description = models.TextField(verbose_name="설명", null=True, blank=True)

    class Meta:
        verbose_name = "상세 제품"
        verbose_name_plural = "상세 제품 목록"
        unique_together = ['solution', 'platform', 'category']

    def __str__(self):
        return f"{self.solution.name} {self.get_platform_display()} {self.get_category_display()}"

    @property
    def platform_color(self):
        colors = {
            'AOS': 'success',
            'IOS': 'info',
            'SERVER': 'primary',
            'MACOS': 'secondary',
            'WEB': 'warning',
            'FLUTTER': 'danger',
        }
        return colors.get(self.platform, 'secondary')
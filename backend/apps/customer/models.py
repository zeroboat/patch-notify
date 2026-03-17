from django.db import models
from apps.base.models import BaseModel


class Customer(BaseModel):
    name = models.CharField(max_length=100, verbose_name="고객사명")
    is_on_premise = models.BooleanField(default=False, verbose_name="On-Premise 설치")
    solutions = models.ManyToManyField('product.Solution', related_name='customers', verbose_name="구매 솔루션", blank=True)

    class Meta:
        verbose_name = "고객사"
        verbose_name_plural = "고객사 목록"

    def __str__(self):
        return self.name


class CustomerEmail(BaseModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='emails', verbose_name="고객사")
    email = models.EmailField(verbose_name="이메일")
    name = models.CharField(max_length=100, verbose_name="담당자명", null=True, blank=True)

    class Meta:
        verbose_name = "고객사 이메일"
        verbose_name_plural = "고객사 이메일 목록"
        unique_together = ['customer', 'email']

    def __str__(self):
        return f"{self.customer.name} - {self.email}"
    



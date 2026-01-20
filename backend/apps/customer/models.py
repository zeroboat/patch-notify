from django.db import models
from apps.base.models import BaseModel
# Create your models here.

class Customer(BaseModel):
    name = models.CharField(max_length=100, verbose_name="이름")
    products = models.ManyToManyField('product.Product', related_name='customers', verbose_name="구독 제품들", blank=True)

    def __str__(self):
        return self.name
    



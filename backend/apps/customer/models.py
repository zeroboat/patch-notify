from django.db import models
from apps.base.models import BaseModel
# Create your models here.

class Customer(BaseModel):
    name = models.CharField(max_length=100, verbose_name="이름")

    def __str__(self):
        return self.name
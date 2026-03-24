from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.base.models import BaseModel


class UserProfile(BaseModel):
    ROLE_ADMIN = 'admin'
    ROLE_DEV = 'dev'
    ROLE_SE = 'se'
    ROLE_GUEST = 'guest'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_DEV, 'Dev'),
        (ROLE_SE, 'SE'),
        (ROLE_GUEST, 'Guest'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='사용자',
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default=ROLE_GUEST,
        verbose_name='역할',
    )

    class Meta:
        verbose_name = '사용자 프로필'
        verbose_name_plural = '사용자 프로필'

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """신규 User 생성 시 UserProfile 자동 생성 (기본 역할: Guest)"""
    if created:
        UserProfile.objects.get_or_create(user=instance)

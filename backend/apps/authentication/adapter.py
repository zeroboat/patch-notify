from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.http import HttpResponseForbidden

ALLOWED_DOMAINS = ['stealien.com']


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email', '')
        domain = email.split('@')[-1]
        if domain not in ALLOWED_DOMAINS:
            raise ImmediateHttpResponse(
                HttpResponseForbidden(f'접근이 허용되지 않은 계정입니다. ({email})')
            )

    def save_user(self, request, sociallogin, form=None):
        existing_password = None
        user = sociallogin.user
        if user.pk:
            try:
                from django.contrib.auth import get_user_model
                existing_password = get_user_model().objects.get(pk=user.pk).password
            except Exception:
                pass

        user = super().save_user(request, sociallogin, form)

        if existing_password:
            user.password = existing_password
            user.save(update_fields=['password'])

        return user

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver


def _get_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')


@receiver(user_logged_in)
def on_login_success(sender, request, user, **kwargs):
    from apps.logs.models import ActionLog
    ActionLog.objects.create(
        actor=user,
        action=ActionLog.LOGIN_SUCCESS,
        target=user.username,
        ip_address=_get_ip(request),
    )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    from apps.logs.models import ActionLog
    username = credentials.get('username') or credentials.get('email') or '(알 수 없음)'
    ActionLog.objects.create(
        actor=None,
        action=ActionLog.LOGIN_FAILED,
        target=username,
        detail={'입력한 계정': username},
        ip_address=_get_ip(request),
    )

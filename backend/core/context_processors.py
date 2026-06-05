from django.conf import settings

from apps.base.mixins import get_user_role


def my_setting(request):
    from apps.config.models import SiteConfig
    try:
        cfg = SiteConfig.get()
        notion_enabled = cfg.notion_enabled
    except Exception:
        notion_enabled = False
    return {'MY_SETTING': settings, 'NOTION_ENABLED': notion_enabled}


# Add the 'ENVIRONMENT' setting to the template context
def environment(request):
    return {'ENVIRONMENT': settings.ENVIRONMENT}


def user_role(request):
    if request.user.is_authenticated:
        return {'user_role': get_user_role(request.user)}
    return {'user_role': 'anonymous'}


def open_feedback_count(request):
    if not request.user.is_authenticated:
        return {'open_feedback_count': 0}
    try:
        from apps.feedback.models import Feedback
        count = Feedback.objects.filter(status='open').count()
        return {'open_feedback_count': count}
    except Exception:
        return {'open_feedback_count': 0}

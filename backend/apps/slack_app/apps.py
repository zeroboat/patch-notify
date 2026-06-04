from django.apps import AppConfig


class SlackAppConfig(AppConfig):
    name = 'apps.slack_app'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import SlackWorkspace
        auditlog.register(SlackWorkspace, exclude_fields=['bot_token'])

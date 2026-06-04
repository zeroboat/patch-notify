from django.apps import AppConfig


class ConfigConfig(AppConfig):
    name = 'apps.config'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import SiteConfig
        auditlog.register(SiteConfig, exclude_fields=[
            'gmail_app_password', 'notion_token', 'nextcloud_password'
        ])

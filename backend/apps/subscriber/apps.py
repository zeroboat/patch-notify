from django.apps import AppConfig


class SubscriberConfig(AppConfig):
    name = 'apps.subscriber'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Subscription
        auditlog.register(Subscription)

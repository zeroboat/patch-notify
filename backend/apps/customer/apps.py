from django.apps import AppConfig


class CustomerConfig(AppConfig):
    name = 'apps.customer'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Customer, CustomerEmail
        auditlog.register(Customer)
        auditlog.register(CustomerEmail)

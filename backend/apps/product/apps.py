from django.apps import AppConfig


class ProductConfig(AppConfig):
    name = 'apps.product'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Solution, Product
        auditlog.register(Solution)
        auditlog.register(Product)

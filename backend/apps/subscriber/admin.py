from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'channel', 'is_active', 'frequency', 'max_items')
    list_filter = ('channel', 'is_active', 'frequency', 'product__solution')
    search_fields = ('customer__name', 'product__solution__name')

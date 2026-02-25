from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'solution', 'channel', 'is_active', 'frequency', 'max_items')
    list_filter = ('channel', 'is_active', 'frequency', 'solution')
    search_fields = ('customer__name', 'solution__name')

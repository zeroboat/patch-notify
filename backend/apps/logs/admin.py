from django.contrib import admin
from .models import DispatchLog


@admin.register(DispatchLog)
class DispatchLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'log_type', 'channel', 'customer', 'solution', 'recipient', 'status')
    list_filter = ('log_type', 'channel', 'status')
    search_fields = ('recipient', 'subject', 'customer__name')
    readonly_fields = ('created_at', 'updated_at')

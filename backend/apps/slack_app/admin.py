from django.contrib import admin
from .models import SlackWorkspace


@admin.register(SlackWorkspace)
class SlackWorkspaceAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'team_id', 'status', 'customer', 'is_internal', 'created_at')
    list_filter = ('status', 'is_internal')
    list_editable = ('status', 'customer', 'is_internal')
    search_fields = ('team_name', 'team_id', 'customer__name')
    readonly_fields = ('team_id', 'team_name', 'bot_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)

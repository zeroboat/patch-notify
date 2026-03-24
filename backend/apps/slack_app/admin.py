from django.contrib import admin
from .models import SlackWorkspace


@admin.register(SlackWorkspace)
class SlackWorkspaceAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'team_id', 'status', 'customer', 'created_at')
    list_filter = ('status',)
    list_editable = ('status', 'customer')
    search_fields = ('team_name', 'team_id', 'customer__name')
    readonly_fields = ('team_id', 'team_name', 'bot_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)

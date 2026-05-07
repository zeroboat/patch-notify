from django.contrib import admin
from .models import Feedback, FeedbackComment


class FeedbackCommentInline(admin.TabularInline):
    model = FeedbackComment
    extra = 0
    readonly_fields = ('author', 'created_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'priority', 'author', 'assignee', 'created_at')
    list_filter = ('category', 'status', 'priority')
    search_fields = ('title', 'content', 'author__username')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    inlines = [FeedbackCommentInline]

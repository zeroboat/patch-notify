from django.contrib import admin
from .models import NotionPageMapping


@admin.register(NotionPageMapping)
class NotionPageMappingAdmin(admin.ModelAdmin):
    list_display = ('product', 'page_id_ko', 'page_id_en', 'updated_at')
    list_select_related = ('product', 'product__solution')
    search_fields = ('product__solution__name',)

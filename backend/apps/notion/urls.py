from django.urls import path
from .views import (
    NotionManagementView,
    create_mapping,
    update_mapping,
    delete_mapping,
    notion_sync,
)

app_name = 'notion'

urlpatterns = [
    path('management/', NotionManagementView.as_view(), name='notion_management'),
    path('mapping/create/', create_mapping, name='create_mapping'),
    path('mapping/update/', update_mapping, name='update_mapping'),
    path('mapping/delete/', delete_mapping, name='delete_mapping'),
    path('sync/', notion_sync, name='notion_sync'),
]

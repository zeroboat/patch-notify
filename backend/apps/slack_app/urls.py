from django.urls import path
from .views import SlackWorkspaceManagementView, update_workspace_status, link_workspace_customer

app_name = 'slack_app'
urlpatterns = [
    path('', SlackWorkspaceManagementView.as_view(), name='slack_workspace_management'),
    path('update-status/', update_workspace_status, name='update_workspace_status'),
    path('link-customer/', link_workspace_customer, name='link_workspace_customer'),
]

from django.urls import path
from .views import DispatchLogView, AuditLogView

app_name = 'logs'

urlpatterns = [
    path('', DispatchLogView.as_view(), name='dispatch_log'),
    path('audit/', AuditLogView.as_view(), name='audit_log'),
]

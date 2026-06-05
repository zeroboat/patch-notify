from django.urls import path
from .views import DispatchLogView, ActionLogView, ActionLogDetailView

app_name = 'logs'

urlpatterns = [
    path('', DispatchLogView.as_view(), name='dispatch_log'),
    path('action/', ActionLogView.as_view(), name='action_log'),
    path('action/<int:pk>/', ActionLogDetailView.as_view(), name='action_log_detail'),
]

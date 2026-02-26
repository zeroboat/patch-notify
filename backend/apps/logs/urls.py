from django.urls import path
from .views import DispatchLogView

app_name = 'logs'

urlpatterns = [
    path('', DispatchLogView.as_view(), name='dispatch_log'),
]

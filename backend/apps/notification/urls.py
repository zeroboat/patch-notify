from django.urls import path
from .views import OfficialNoticeView

app_name = 'notification'

urlpatterns = [
    path('official-notice/', OfficialNoticeView.as_view(), name='official_notice'),
]

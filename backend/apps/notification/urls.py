from django.urls import path
from .views import OfficialNoticeView

app_name = 'notification'

urlpatterns = [
    path('official_notice/', OfficialNoticeView.as_view(), name='official_notice'),
]

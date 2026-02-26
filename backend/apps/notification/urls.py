from django.urls import path
from .views import OfficialNoticeView, get_recipients_preview, send_notice

app_name = 'notification'

urlpatterns = [
    path('official_notice/', OfficialNoticeView.as_view(), name='official_notice'),
    path('recipients_preview/', get_recipients_preview, name='recipients_preview'),
    path('send/', send_notice, name='send_notice'),
]

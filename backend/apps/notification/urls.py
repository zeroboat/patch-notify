from django.urls import path
from .views import OfficialNoticeView, NoticeConfigView, get_recipients_preview, send_notice, preview_email, preview_patchnote_email, get_products_for_preview, get_versions_for_preview, view_notice

app_name = 'notification'

urlpatterns = [
    path('official_notice/', OfficialNoticeView.as_view(), name='official_notice'),
    path('config/', NoticeConfigView.as_view(), name='notice_config'),
    path('config/save/', NoticeConfigView.as_view(), name='notice_config_save'),
    path('recipients_preview/', get_recipients_preview, name='recipients_preview'),
    path('send/', send_notice, name='send_notice'),
    path('preview/', preview_email, name='preview_email'),
    path('preview/patchnote/', preview_patchnote_email, name='preview_patchnote_email'),
    path('preview/patchnote/products/', get_products_for_preview, name='preview_products'),
    path('preview/patchnote/versions/', get_versions_for_preview, name='preview_versions'),
    path('notice/<int:notice_id>/', view_notice, name='view_notice'),
]

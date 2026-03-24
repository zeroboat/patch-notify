from django.urls import path
from .views import (
    PatchNoteDetailView,
    patch_note_append,
    get_patch_note_data,
    patch_note_update,
    patch_note_delete,
    patch_note_publish,
    translation_status,
    patch_note_file_upload,
    patch_note_file_download,
    patch_note_file_delete,
    patch_note_files_list,
)

app_name = 'patchnote'

urlpatterns = [
    path('product/<int:product_id>/', PatchNoteDetailView.as_view(), name='product_patch_detail'),
    path('append', patch_note_append, name='patch_note_append'),
    path('data/<int:patch_note_id>/', get_patch_note_data, name='patch_note_data'),
    path('update/', patch_note_update, name='patch_note_update'),
    path('delete/', patch_note_delete, name='patch_note_delete'),
    path('publish/', patch_note_publish, name='patch_note_publish'),
    path('translation-status/<int:patch_note_id>/', translation_status, name='translation_status'),
    path('file/upload/', patch_note_file_upload, name='file_upload'),
    path('file/download/<int:file_id>/', patch_note_file_download, name='file_download'),
    path('file/delete/', patch_note_file_delete, name='file_delete'),
    path('file/list/<int:patch_note_id>/', patch_note_files_list, name='file_list'),
]

from django.urls import path
from .views import (
    PatchNoteDetailView,
    patch_note_append,
    get_patch_note_data,
    patch_note_update,
    patch_note_delete,
)

app_name = 'patchnote'

urlpatterns = [
    path('product/<int:product_id>/', PatchNoteDetailView.as_view(), name='product_patch_detail'),
    path('append', patch_note_append, name='patch_note_append'),
    path('data/<int:patch_note_id>/', get_patch_note_data, name='patch_note_data'),
    path('update/', patch_note_update, name='patch_note_update'),
    path('delete/', patch_note_delete, name='patch_note_delete'),
]

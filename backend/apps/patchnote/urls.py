from django.urls import path
from .views import PatchNoteDetailView, patch_note_append

app_name = 'patchnote'

urlpatterns = [
    path('product/<int:product_id>/', PatchNoteDetailView.as_view(), name='product_patch_detail'),
    path('append', patch_note_append, name='patch_note_append'),
]

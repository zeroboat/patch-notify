from django.urls import path
from .views import PatchNoteDetailView

app_name = 'patchnote'

urlpatterns = [
    path('product/<int:product_id>/', PatchNoteDetailView.as_view(), name='product_patch_detail'),
]

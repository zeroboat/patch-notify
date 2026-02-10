from django.urls import path
from .views import ProductManagementView

app_name = 'product'

urlpatterns = [
    path('management/', ProductManagementView.as_view(), name='product_management'),
]

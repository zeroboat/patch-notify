from django.urls import path
from .views import ProductManagementView, create_solution, create_product

app_name = 'product'

urlpatterns = [
    path('management/', ProductManagementView.as_view(), name='product_management'),
    path('solution/create/', create_solution, name='create_solution'),
    path('product/create/', create_product, name='create_product'),
]

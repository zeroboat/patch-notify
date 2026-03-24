from django.urls import path
from .views import ProductManagementView, create_solution, update_solution, create_product, update_product, delete_product, delete_solution

app_name = 'product'

urlpatterns = [
    path('management/', ProductManagementView.as_view(), name='product_management'),
    path('solution/create/', create_solution, name='create_solution'),
    path('solution/update/', update_solution, name='update_solution'),
    path('solution/delete/', delete_solution, name='delete_solution'),
    path('product/create/', create_product, name='create_product'),
    path('product/update/', update_product, name='update_product'),
    path('product/delete/', delete_product, name='delete_product'),
]

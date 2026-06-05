from django.urls import path
from .views import (
    ProductManagementView, create_solution, update_solution, create_product,
    update_product, delete_product, delete_solution,
    UtilityManagementView, create_utility_solution, update_utility_solution,
    delete_utility_solution, create_utility, update_utility, delete_utility,
)

app_name = 'product'

urlpatterns = [
    path('management/', ProductManagementView.as_view(), name='product_management'),
    path('solution/create/', create_solution, name='create_solution'),
    path('solution/update/', update_solution, name='update_solution'),
    path('solution/delete/', delete_solution, name='delete_solution'),
    path('product/create/', create_product, name='create_product'),
    path('product/update/', update_product, name='update_product'),
    path('product/delete/', delete_product, name='delete_product'),
    path('utility/', UtilityManagementView.as_view(), name='utility_management'),
    path('utility/solution/create/', create_utility_solution, name='create_utility_solution'),
    path('utility/solution/update/', update_utility_solution, name='update_utility_solution'),
    path('utility/solution/delete/', delete_utility_solution, name='delete_utility_solution'),
    path('utility/create/', create_utility, name='create_utility'),
    path('utility/update/', update_utility, name='update_utility'),
    path('utility/delete/', delete_utility, name='delete_utility'),
]

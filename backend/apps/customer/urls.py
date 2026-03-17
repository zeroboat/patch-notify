from django.urls import path
from .views import (
    CustomerManagementView, create_customer, update_customer, delete_customer,
    add_email, delete_email, import_csv,
)

app_name = 'customer'

urlpatterns = [
    path('', CustomerManagementView.as_view(), name='customer_management'),
    path('create/', create_customer, name='create_customer'),
    path('update/', update_customer, name='update_customer'),
    path('delete/', delete_customer, name='delete_customer'),
    path('email/add/', add_email, name='add_email'),
    path('email/delete/', delete_email, name='delete_email'),
    path('import-csv/', import_csv, name='import_csv'),
]

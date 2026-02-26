from django.urls import path
from .views import SubscriberManagementView, get_customer_subscriptions, save_customer_subscription

app_name = 'subscriber'

urlpatterns = [
    path('', SubscriberManagementView.as_view(), name='subscriber_management'),
    path('subscriptions/<int:customer_id>/', get_customer_subscriptions, name='get_subscriptions'),
    path('save/', save_customer_subscription, name='save_subscription'),
]

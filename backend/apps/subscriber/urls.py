from django.urls import path
from .views import (
    SubscriberManagementView,
    get_customer_subscriptions,
    save_customer_subscription,
    admin_add_subscription_email,
    admin_remove_subscription_email,
    issue_token,
    revoke_token,
    subscribe_page,
    subscribe_toggle_solution,
    subscribe_add_email,
    subscribe_remove_email,
)

app_name = 'subscriber'

urlpatterns = [
    path('', SubscriberManagementView.as_view(), name='subscriber_management'),
    path('subscriptions/<int:customer_id>/', get_customer_subscriptions, name='get_subscriptions'),
    path('save/', save_customer_subscription, name='save_subscription'),
    path('subscription-emails/<int:customer_id>/add/', admin_add_subscription_email, name='admin_add_subscription_email'),
    path('subscription-emails/<int:customer_id>/remove/', admin_remove_subscription_email, name='admin_remove_subscription_email'),
    path('token/issue/<int:customer_id>/', issue_token, name='issue_token'),
    path('token/revoke/<int:customer_id>/', revoke_token, name='revoke_token'),
    path('subscribe/<uuid:token>/', subscribe_page, name='subscribe_page'),
    path('subscribe/<uuid:token>/toggle-solution/', subscribe_toggle_solution, name='subscribe_toggle_solution'),
    path('subscribe/<uuid:token>/add-email/', subscribe_add_email, name='subscribe_add_email'),
    path('subscribe/<uuid:token>/remove-email/', subscribe_remove_email, name='subscribe_remove_email'),
]

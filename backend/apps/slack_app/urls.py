from django.urls import path
from . import views

app_name = 'slack_app'

urlpatterns = [
    path('install/', views.slack_install, name='install'),
    path('oauth/callback/', views.slack_oauth_callback, name='oauth_callback'),
    path('events/', views.slack_events, name='events'),
]

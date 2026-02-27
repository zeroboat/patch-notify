from django.urls import path
from django.contrib.auth.views import LogoutView

from .views import UserLoginView, AuthView, RegisterView


urlpatterns = [
    path(
        "auth/login/",
        UserLoginView.as_view(template_name="auth_login_basic.html"),
        name="auth-login-basic",
    ),
    path(
        "auth/register/",
        RegisterView.as_view(),
        name="auth-register-basic",
    ),
    path(
        "auth/forgot_password/",
        AuthView.as_view(template_name="auth_forgot_password_basic.html"),
        name="auth-forgot-password-basic",
    ),
    path(
        "auth/logout/",
        LogoutView.as_view(),
        name="auth-logout",
    ),
]

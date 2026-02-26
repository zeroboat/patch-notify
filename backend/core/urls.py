"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("patchnote/", include(("apps.patchnote.urls", "patchnote"), namespace="patchnote")),
    path("notification/", include(("apps.notification.urls", "notification"), namespace="notification")),
    path("product/", include(("apps.product.urls", "product"), namespace="product")),
    path("customer/", include(("apps.customer.urls", "customer"), namespace="customer")),
    path("subscriber/", include(("apps.subscriber.urls", "subscriber"), namespace="subscriber")),
    path("logs/", include(("apps.logs.urls", "logs"), namespace="logs")),
    path("slack/", include(("apps.slack_app.urls", "slack_app"), namespace="slack_app")),

    path("", include("apps.dashboards.urls")),
    path("", include("apps.authentication.urls")),
]

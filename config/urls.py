"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import: from my_app import views
    2. Add a URL to urlpatterns: path('', views.dashboard, name='dashboard')
Class-based views
    1. Add an import: from other_app.views import Dashboard
    2. Add a URL to urlpatterns: path('', Dashboard.as_view(), name='dashboard')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns: path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("api/", include("api.urls")),
    path("", include("dashboard.urls")),
    path("", include("dmm_panel.urls")),
    path("", include("tasks.urls")),
    path("", include("accounts.urls")),
    path("", include("instruments.urls")),
    path("", include("measurements.urls")),
]

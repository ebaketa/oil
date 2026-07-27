"""Compatibility URL aggregator for the domain applications."""

from django.urls import include, path

urlpatterns = [
    path("", include("dashboard.urls")),
    path("", include("accounts.urls")),
    path("", include("instruments.urls")),
    path("", include("measurements.urls")),
]

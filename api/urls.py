"""URL routes for the OIL JSON API."""

from django.urls import path

from . import views

urlpatterns = [
    path("instruments/", views.instrument_list, name="api_instrument_list"),
    path(
        "instruments/<int:pk>/",
        views.instrument_detail,
        name="api_instrument_detail",
    ),
    path(
        "measurements/",
        views.measurement_list,
        name="api_measurement_list",
    ),
    path(
        "measurements/single/",
        views.measurement_single,
        name="api_measurement_single",
    ),
]

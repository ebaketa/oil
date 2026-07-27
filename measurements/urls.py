"""URL routes for measurement workflows."""

from django.urls import path

from . import exports, views

urlpatterns = [
    path("measurements/", views.measurement_list, name="measurement_list"),
    path(
        "measurements/export.csv",
        exports.measurement_export_csv,
        name="measurement_export_csv",
    ),
    path(
        "measurements/single/",
        views.measurement_create,
        name="measurement_create",
    ),
    path(
        "measurements/single/result/",
        views.measurement_single_result,
        name="measurement_single_result",
    ),
    path(
        "measurements/loop/",
        views.measurement_loop,
        name="measurement_loop",
    ),
    path(
        "measurements/continuous/",
        views.measurement_continuous,
        name="measurement_continuous",
    ),
    path(
        "measurements/continuous/stream/",
        views.measurement_continuous_stream,
        name="measurement_continuous_stream",
    ),
    path(
        "measurements/continuous/stop/",
        views.measurement_continuous_stop,
        name="measurement_continuous_stop",
    ),
    path(
        "measurements/loop/stream/",
        views.measurement_loop_stream,
        name="measurement_loop_stream",
    ),
]

"""URL routes for measurement tasks."""

from django.urls import path

from . import views

urlpatterns = [
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/stop/", views.task_stop, name="task_stop"),
    path(
        "tasks/<int:pk>/complete/",
        views.task_complete,
        name="task_complete",
    ),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path(
        "tasks/<int:pk>/export.csv",
        views.task_export_csv,
        name="task_export_csv",
    ),
]

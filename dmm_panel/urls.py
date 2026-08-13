from django.urls import path

from . import views

urlpatterns = [
    path("panels/", views.panel_list, name="panel_list"),
    path("dmm/<int:pk>/", views.panel, name="dmm_panel"),
    path("dmm/<int:pk>/measure/", views.measure, name="dmm_panel_measure"),
    path("dmm/<int:pk>/live/", views.live_reading, name="dmm_panel_live"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("panels/", views.panel_list, name="panel_list"),
    path("dmm/<int:pk>/", views.panel, name="dmm_panel"),
    path("dmm/<int:pk>/status/", views.status, name="dmm_panel_status"),
    path("dmm/<int:pk>/resolution/", views.resolution, name="dmm_panel_resolution"),
    path("dmm/<int:pk>/nplc/", views.nplc, name="dmm_panel_nplc"),
    path("dmm/<int:pk>/clear/", views.clear_status, name="dmm_panel_clear"),
    path("dmm/<int:pk>/release/", views.release, name="dmm_panel_release"),
    path("dmm/<int:pk>/measure/", views.measure, name="dmm_panel_measure"),
    path("dmm/<int:pk>/live/", views.live_reading, name="dmm_panel_live"),
    path("bmx280/<int:pk>/measure/", views.bmx280_measure, name="bmx280_measure"),
]

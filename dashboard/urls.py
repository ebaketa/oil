"""URL routes for dashboard and informational pages."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("contact/", views.contact, name="contact"),
    path("about/", views.about, name="about"),
]

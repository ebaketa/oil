from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path('profile/', views.profile, name='profile'),
    path('instruments/', views.instrument_list, name='instrument_list'),
    path('instruments/add/', views.instrument_create, name='instrument_create'),
]

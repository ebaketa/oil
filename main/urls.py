from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path('profile/', views.profile, name='profile'),
    path('instruments/', views.instrument_list, name='instrument_list'),
    path('instruments/add/', views.instrument_create, name='instrument_create'),
    path('measurements/', views.measurement_list, name='measurement_list'),
    path(
        'measurements/new/',
        views.measurement_create,
        name='measurement_create',
    ),
    path(
        'measurements/single/result/',
        views.measurement_single_result,
        name='measurement_single_result',
    ),
    path(
        'measurements/loop/',
        views.measurement_loop,
        name='measurement_loop',
    ),
    path(
        'measurements/continuous/',
        views.measurement_continuous,
        name='measurement_continuous',
    ),
    path(
        'measurements/continuous/stream/',
        views.measurement_continuous_stream,
        name='measurement_continuous_stream',
    ),
    path(
        'measurements/continuous/stop/',
        views.measurement_continuous_stop,
        name='measurement_continuous_stop',
    ),
    path(
        'measurements/loop/stream/',
        views.measurement_loop_stream,
        name='measurement_loop_stream',
    ),
    path(
        'instruments/<int:pk>/edit/',
        views.instrument_edit,
        name='instrument_edit',
    ),
    path(
        'instruments/<int:pk>/driver/',
        views.instrument_driver,
        name='instrument_driver',
    ),
    path(
        'instruments/<int:pk>/connect/',
        views.instrument_connect,
        name='instrument_connect',
    ),
    path(
        'instruments/<int:pk>/disconnect/',
        views.instrument_disconnect,
        name='instrument_disconnect',
    ),
    path(
        'instruments/<int:pk>/driver/test/',
        views.instrument_driver_test,
        name='instrument_driver_test',
    ),
    path(
        'instruments/<int:pk>/driver/test/dcv/',
        views.instrument_driver_test_dcv,
        name='instrument_driver_test_dcv',
    ),
]

from django.urls import path

from . import views

urlpatterns = [
    path("", views.public_home, name="public_home"),
    path("report/", views.report, name="report"),
    path("track/<int:pk>/", views.track, name="track"),

    path("control/", views.dashboard, name="dashboard"),
    path("control/queue/", views.queue, name="queue"),
    path("control/request/<int:pk>/", views.request_detail, name="request_detail"),
    path("control/request/<int:pk>/move/", views.move, name="move"),
    path("control/request/<int:pk>/dispatch/", views.plan_dispatch, name="plan_dispatch"),
    path("control/request/<int:pk>/override/", views.override, name="override"),
    path("control/request/<int:pk>/rescore/", views.rescore, name="rescore"),
    path("control/map/", views.map_view, name="map"),
    path("control/map.json", views.map_json, name="map_json"),

    path("my-reports/", views.my_reports, name="my_reports"),
]

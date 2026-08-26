from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.portal.urls")),
    path("gateway/", include("apps.gateway.urls")),
    path("", include("django.contrib.auth.urls")),
]

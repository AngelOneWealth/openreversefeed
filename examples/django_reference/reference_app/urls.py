from django.urls import include, path

urlpatterns = [
    path("", include("dashboard.urls")),
    path("uploads/", include("uploads.urls")),
    path("corrections/", include("corrections.urls")),
]

from django.urls import path

from . import views

app_name = "uploads"

urlpatterns = [
    path("", views.file_list, name="list"),
    path("new/", views.upload_view, name="new"),
    path("<int:source_file_id>/", views.file_detail, name="detail"),
    path("<int:source_file_id>/process/", views.process_view, name="process"),
]

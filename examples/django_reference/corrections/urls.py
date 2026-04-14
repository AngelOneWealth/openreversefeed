from django.urls import path

from . import views

app_name = "corrections"

urlpatterns = [
    path("", views.queue_list, name="list"),
]

from django.urls import path

from . import views

app_name = "metrics"

urlpatterns = [
    path("", views.snapshot_list, name="list"),
    path("new/", views.snapshot_create, name="create"),
    path("<int:snapshot_id>/delete/", views.snapshot_delete, name="delete"),
    path("profile/", views.profile_edit, name="profile"),
    path("goals/", views.goal_edit, name="goals"),
]

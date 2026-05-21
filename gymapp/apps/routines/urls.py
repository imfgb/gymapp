from django.urls import path

from . import views

app_name = "routines"

urlpatterns = [
    path("", views.routine_list, name="list"),
    path("new/", views.routine_create, name="create"),
    path("preview/", views.routine_preview, name="preview"),
    path("<int:routine_id>/", views.routine_detail, name="detail"),
    path("<int:routine_id>/edit/", views.routine_edit, name="edit"),
    path("<int:routine_id>/delete/", views.routine_delete, name="delete"),
    # Day
    path("<int:routine_id>/days/add/", views.day_add, name="day_add"),
    path(
        "<int:routine_id>/days/<int:day_id>/delete/",
        views.day_delete,
        name="day_delete",
    ),
    # Exercise within a day
    path(
        "<int:routine_id>/days/<int:day_id>/exercises/add/",
        views.exercise_add,
        name="exercise_add",
    ),
    path(
        "<int:routine_id>/days/<int:day_id>/exercises/<int:rex_id>/update/",
        views.exercise_update,
        name="exercise_update",
    ),
    path(
        "<int:routine_id>/days/<int:day_id>/exercises/<int:rex_id>/delete/",
        views.exercise_delete,
        name="exercise_delete",
    ),
    # Weekly split
    path("split/", views.weekly_split, name="weekly_split"),
    path("split/<int:weekday>/", views.weekly_split_assign, name="weekly_split_assign"),
]

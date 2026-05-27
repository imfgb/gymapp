from django.urls import path

from . import views

app_name = "injuries"

urlpatterns = [
    path("", views.injury_list, name="list"),
    path("nueva/", views.injury_create, name="create"),
    path("<int:injury_id>/editar/", views.injury_edit, name="edit"),
    path("<int:injury_id>/toggle/", views.injury_toggle_resolved, name="toggle"),
    path("<int:injury_id>/borrar/", views.injury_delete, name="delete"),
    path("<int:injury_id>/avoid/", views.avoid_add, name="avoid_add"),
    path(
        "<int:injury_id>/avoid/<int:exercise_id>/quitar/",
        views.avoid_remove,
        name="avoid_remove",
    ),
]

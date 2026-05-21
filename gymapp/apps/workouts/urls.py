from django.urls import path

from . import views

app_name = "workouts"

urlpatterns = [
    path("", views.history, name="history"),
    path("start/", views.start, name="start"),
    path("<int:session_id>/", views.session, name="session"),
    path("<int:session_id>/finish/", views.finish, name="finish"),
    # Set-level
    path(
        "<int:session_id>/sets/<int:set_id>/complete/",
        views.complete_set_view,
        name="complete_set",
    ),
    path(
        "<int:session_id>/sets/<int:set_id>/update/",
        views.update_set_view,
        name="update_set",
    ),
    path(
        "<int:session_id>/sets/<int:set_id>/delete/",
        views.delete_set_view,
        name="delete_set",
    ),
    # Exercise-level
    path(
        "<int:session_id>/exercises/add/",
        views.add_exercise_view,
        name="add_exercise",
    ),
    path(
        "<int:session_id>/exercises/add-custom/",
        views.add_custom_exercise_view,
        name="add_custom_exercise",
    ),
    path(
        "<int:session_id>/exercises/<int:elog_id>/sets/add/",
        views.add_set_view,
        name="add_set",
    ),
    path(
        "<int:session_id>/exercises/<int:elog_id>/swap/",
        views.swap_exercise_view,
        name="swap_exercise",
    ),
    path(
        "<int:session_id>/exercises/<int:elog_id>/delete/",
        views.delete_exercise_log_view,
        name="delete_exercise_log",
    ),
]

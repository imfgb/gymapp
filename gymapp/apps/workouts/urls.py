from django.urls import path

from . import views

app_name = "workouts"

urlpatterns = [
    path("", views.history, name="history"),
    path("start/", views.start, name="start"),
    path("<int:session_id>/", views.session, name="session"),
    path("<int:session_id>/finish/", views.finish, name="finish"),
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
        "<int:session_id>/exercises/<int:elog_id>/swap/",
        views.swap_exercise_view,
        name="swap_exercise",
    ),
]

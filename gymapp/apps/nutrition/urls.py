from django.urls import path

from . import views

app_name = "nutrition"

urlpatterns = [
    path("", views.home, name="home"),
    path("preferencias/", views.preferences, name="preferences"),
    path("comidas/generar/", views.generate_meal_view, name="generate_meal"),
    path("comidas/<int:meal_id>/hecha/", views.meal_mark_done, name="meal_done"),
    path("comidas/<int:meal_id>/eliminar/", views.meal_delete, name="meal_delete"),
]

from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("", views.onboarding, name="onboarding"),
    path("skip/", views.onboarding_skip, name="onboarding_skip"),
]

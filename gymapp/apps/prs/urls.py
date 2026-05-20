from django.urls import path

from . import views

app_name = "prs"

urlpatterns = [
    path("", views.pr_list, name="list"),
    path("new/", views.pr_create, name="create"),
    path("<slug:slug>/", views.pr_detail, name="detail"),
    path("<int:pr_id>/edit/", views.pr_edit, name="edit"),
    path("<int:pr_id>/delete/", views.pr_delete, name="delete"),
]

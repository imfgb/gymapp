from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("report/", views.report, name="report"),
    path("admin/", views.admin_list, name="admin"),
    path("admin/<int:report_id>/status/", views.admin_status, name="admin_status"),
    path("admin/<int:report_id>/delete/", views.admin_delete, name="admin_delete"),
    # Token-authenticated JSON API (admin triage automation):
    path("api/bugs/", views.api_bugs, name="api_bugs"),
    path("api/bugs/<int:report_id>/status/", views.api_bug_status, name="api_bug_status"),
]

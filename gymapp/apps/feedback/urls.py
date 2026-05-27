from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("report/", views.report, name="report"),
    path("admin/", views.admin_list, name="admin"),
    path("admin/<int:report_id>/status/", views.admin_status, name="admin_status"),
    path("admin/<int:report_id>/delete/", views.admin_delete, name="admin_delete"),
]

"""Root URL configuration.

Each Django app owns a `urls.py` and is mounted below. The dashboard owns the
root URL (`/`); auth views live under `/auth/`; the admin under `/admin/`.
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "auth/login/",
        auth_views.LoginView.as_view(template_name="auth/login.html"),
        name="login",
    ),
    path("auth/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "auth/password/change/",
        auth_views.PasswordChangeView.as_view(template_name="auth/password_change.html"),
        name="password_change",
    ),
    path(
        "auth/password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="auth/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("workouts/", include("gymapp.apps.workouts.urls")),
    path("", include("gymapp.apps.dashboard.urls")),
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass

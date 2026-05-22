"""Admin defaults.

Subclass `OwnerScopedAdmin` for any model whose rows are user-owned so that
non-superusers only see their own rows in `/admin`.
"""

from django.contrib import admin


class OwnerScopedAdmin(admin.ModelAdmin):
    """Filters the admin list view by the request user's ownership."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(owner=request.user)

    def save_model(self, request, obj, form, change):
        if not change and getattr(obj, "owner_id", None) is None:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

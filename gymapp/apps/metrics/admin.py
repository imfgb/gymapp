from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import UserMetricSnapshot


@admin.register(UserMetricSnapshot)
class UserMetricSnapshotAdmin(OwnerScopedAdmin):
    list_display = ("owner", "measured_at", "weight_kg", "body_fat_pct")
    list_filter = ("owner",)
    date_hierarchy = "measured_at"
    autocomplete_fields = ("owner",)

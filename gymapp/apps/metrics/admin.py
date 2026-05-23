from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import MonthlyGoal, UserMetricSnapshot


@admin.register(UserMetricSnapshot)
class UserMetricSnapshotAdmin(OwnerScopedAdmin):
    list_display = ("owner", "measured_at", "weight_kg", "body_fat_pct")
    list_filter = ("owner",)
    date_hierarchy = "measured_at"
    autocomplete_fields = ("owner",)


@admin.register(MonthlyGoal)
class MonthlyGoalAdmin(OwnerScopedAdmin):
    list_display = (
        "owner",
        "year",
        "month",
        "target_sessions",
        "target_volume_kg",
        "target_bodyweight_kg",
    )
    list_filter = ("owner", "year", "month")
    autocomplete_fields = ("owner",)

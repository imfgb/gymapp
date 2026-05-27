from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import FatigueAdjustment, MonthlyGoal, ReadinessSnapshot, UserMetricSnapshot


@admin.register(UserMetricSnapshot)
class UserMetricSnapshotAdmin(OwnerScopedAdmin):
    list_display = (
        "owner", "measured_at", "weight_kg", "body_fat_pct", "muscle_pct", "visceral_fat",
    )
    list_filter = ("owner",)
    date_hierarchy = "measured_at"
    autocomplete_fields = ("owner",)


@admin.register(ReadinessSnapshot)
class ReadinessSnapshotAdmin(OwnerScopedAdmin):
    list_display = ("owner", "date", "sleep_quality", "stress_level", "soreness_overall")
    list_filter = ("owner",)
    date_hierarchy = "date"
    autocomplete_fields = ("owner",)


@admin.register(FatigueAdjustment)
class FatigueAdjustmentAdmin(OwnerScopedAdmin):
    list_display = ("owner", "date", "muscle_slug", "delta")
    list_filter = ("owner", "muscle_slug")
    autocomplete_fields = ("owner",)


@admin.register(MonthlyGoal)
class MonthlyGoalAdmin(OwnerScopedAdmin):
    list_display = (
        "owner",
        "year",
        "month",
        "target_sessions",
        "target_bodyweight_kg",
    )
    list_filter = ("owner", "year", "month")
    autocomplete_fields = ("owner",)

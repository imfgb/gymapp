from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import Injury


@admin.register(Injury)
class InjuryAdmin(OwnerScopedAdmin):
    list_display = ("owner", "name", "body_region", "severity", "started_on", "resolved_on")
    list_filter = ("owner", "body_region", "severity")
    date_hierarchy = "started_on"
    autocomplete_fields = ("owner",)
    filter_horizontal = ("avoid_exercises",)

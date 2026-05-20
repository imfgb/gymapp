from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import PersonalRecord


@admin.register(PersonalRecord)
class PersonalRecordAdmin(OwnerScopedAdmin):
    list_display = ("owner", "exercise", "weight_kg", "reps", "achieved_at", "source")
    list_filter = ("source", "exercise")
    search_fields = ("exercise__name",)
    autocomplete_fields = ("owner", "exercise")
    raw_id_fields = ("source_set",)
    date_hierarchy = "achieved_at"

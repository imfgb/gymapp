from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import SavedMeal, Supplement


@admin.register(SavedMeal)
class SavedMealAdmin(OwnerScopedAdmin):
    list_display = ("owner", "slot", "calories", "eaten_at", "created_at")
    list_filter = ("owner", "slot")
    autocomplete_fields = ("owner",)


@admin.register(Supplement)
class SupplementAdmin(OwnerScopedAdmin):
    list_display = ("owner", "name", "last_taken_at")
    list_filter = ("owner",)
    autocomplete_fields = ("owner",)

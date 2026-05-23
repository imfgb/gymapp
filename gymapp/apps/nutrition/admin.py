from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import SavedMeal


@admin.register(SavedMeal)
class SavedMealAdmin(OwnerScopedAdmin):
    list_display = ("owner", "slot", "calories", "eaten_at", "created_at")
    list_filter = ("owner", "slot")
    autocomplete_fields = ("owner",)

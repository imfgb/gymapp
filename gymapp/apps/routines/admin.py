"""Routines admin. Owner-scoped — non-superusers see only their own rows."""
from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import Routine, RoutineDay, RoutineExercise, WeeklySplit


class RoutineExerciseInline(admin.TabularInline):
    model = RoutineExercise
    extra = 0
    autocomplete_fields = ("exercise",)


class RoutineDayInline(admin.StackedInline):
    model = RoutineDay
    extra = 0
    show_change_link = True


@admin.register(Routine)
class RoutineAdmin(OwnerScopedAdmin):
    list_display = ("name", "owner", "training_style", "is_archived", "created_at")
    list_filter = ("training_style", "is_archived")
    search_fields = ("name",)
    inlines = [RoutineDayInline]
    autocomplete_fields = ("owner",)


@admin.register(RoutineDay)
class RoutineDayAdmin(admin.ModelAdmin):
    list_display = ("label", "routine", "ordering")
    list_filter = ("routine",)
    search_fields = ("label", "routine__name")
    inlines = [RoutineExerciseInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(routine__owner=request.user)


@admin.register(WeeklySplit)
class WeeklySplitAdmin(OwnerScopedAdmin):
    list_display = ("owner", "weekday", "routine_day")
    list_filter = ("weekday",)
    autocomplete_fields = ("owner", "routine_day")

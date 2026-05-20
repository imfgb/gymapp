"""Admin for workouts. Owner-scoped through the session."""
from django.contrib import admin

from gymapp.apps.core.admin import OwnerScopedAdmin

from .models import ExerciseLog, SetLog, WorkoutSession


class SetLogInline(admin.TabularInline):
    model = SetLog
    extra = 0


class ExerciseLogInline(admin.StackedInline):
    model = ExerciseLog
    extra = 0
    autocomplete_fields = ("exercise",)
    show_change_link = True


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(OwnerScopedAdmin):
    list_display = ("id", "owner", "started_at", "status", "source_routine_day")
    list_filter = ("status",)
    date_hierarchy = "started_at"
    inlines = [ExerciseLogInline]
    autocomplete_fields = ("owner", "source_routine_day")


@admin.register(ExerciseLog)
class ExerciseLogAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "exercise", "ordering")
    search_fields = ("exercise__name",)
    autocomplete_fields = ("exercise",)
    inlines = [SetLogInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(session__owner=request.user)


@admin.register(SetLog)
class SetLogAdmin(admin.ModelAdmin):
    list_display = ("id", "exercise_log", "ordering", "weight_kg", "reps", "completed_at")
    list_filter = ("is_warmup", "completed_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(exercise_log__session__owner=request.user)

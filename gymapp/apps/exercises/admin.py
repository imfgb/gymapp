"""Admin for the exercise catalogue.

Global exercises (owner=NULL) are visible to all staff; per-user custom
exercises are visible only to their owner unless the staffer is a superuser.
"""
from django.contrib import admin

from .models import Equipment, Exercise, ExerciseAlternative, MuscleGroup


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "region")
    list_filter = ("region",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ExerciseAlternativeInline(admin.TabularInline):
    model = ExerciseAlternative
    fk_name = "from_exercise"
    extra = 0
    autocomplete_fields = ("to_exercise",)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("name", "equipment", "category", "owner", "is_active")
    list_filter = ("category", "equipment", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("primary_muscles", "secondary_muscles")
    inlines = [ExerciseAlternativeInline]
    autocomplete_fields = ("equipment", "owner")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Non-superuser staff see globals + their own customs.
        from django.db.models import Q

        return qs.filter(Q(owner__isnull=True) | Q(owner=request.user))

    def save_model(self, request, obj, form, change):
        # New rows created by a non-superuser default to that user's ownership.
        if not change and obj.owner_id is None and not request.user.is_superuser:
            obj.owner = request.user
        super().save_model(request, obj, form, change)


@admin.register(ExerciseAlternative)
class ExerciseAlternativeAdmin(admin.ModelAdmin):
    list_display = ("from_exercise", "to_exercise", "reason")
    search_fields = ("from_exercise__name", "to_exercise__name")
    autocomplete_fields = ("from_exercise", "to_exercise")

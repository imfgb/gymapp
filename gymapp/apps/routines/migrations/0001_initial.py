"""Initial schema for `routines`. Depends on `users` and `exercises`."""
import django.core.validators
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exercises", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Routine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                (
                    "training_style",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Snapshot of the user's training_style at routine creation. "
                            "Updates to the user's profile don't backfill here."
                        ),
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("is_archived", models.BooleanField(default=False)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="routines_routine_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="RoutineDay",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "label",
                    models.CharField(help_text="e.g. 'Push A', 'Lower'", max_length=60),
                ),
                ("ordering", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                (
                    "routine",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="days",
                        to="routines.routine",
                    ),
                ),
            ],
            options={"ordering": ["routine", "ordering", "id"]},
        ),
        migrations.CreateModel(
            name="RoutineExercise",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("ordering", models.PositiveSmallIntegerField(default=0)),
                (
                    "target_sets",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(50),
                        ]
                    ),
                ),
                (
                    "target_reps_low",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(100),
                        ]
                    ),
                ),
                (
                    "target_reps_high",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(100),
                        ]
                    ),
                ),
                (
                    "target_weight_kg",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=5, null=True
                    ),
                ),
                (
                    "rest_seconds",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text=(
                            "Override; falls back to Profile.default_rest_seconds when NULL."
                        ),
                        null=True,
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=200)),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="routine_uses",
                        to="exercises.exercise",
                    ),
                ),
                (
                    "routine_day",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="exercises",
                        to="routines.routineday",
                    ),
                ),
            ],
            options={"ordering": ["routine_day", "ordering", "id"]},
        ),
        migrations.CreateModel(
            name="WeeklySplit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Monday"),
                            (1, "Tuesday"),
                            (2, "Wednesday"),
                            (3, "Thursday"),
                            (4, "Friday"),
                            (5, "Saturday"),
                            (6, "Sunday"),
                        ]
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="weekly_splits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "routine_day",
                    models.ForeignKey(
                        blank=True,
                        help_text="NULL = rest day.",
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="scheduled_in",
                        to="routines.routineday",
                    ),
                ),
            ],
            options={"ordering": ["owner", "weekday"]},
        ),
        migrations.AddConstraint(
            model_name="routine",
            constraint=models.UniqueConstraint(
                fields=("owner", "name"), name="routines_unique_name_per_owner"
            ),
        ),
        migrations.AddConstraint(
            model_name="routineday",
            constraint=models.UniqueConstraint(
                fields=("routine", "label"), name="routines_unique_day_label_per_routine"
            ),
        ),
        migrations.AddConstraint(
            model_name="routineexercise",
            constraint=models.CheckConstraint(
                check=models.Q(("target_reps_low__lte", models.F("target_reps_high"))),
                name="routines_reps_low_lte_high",
            ),
        ),
        migrations.AddConstraint(
            model_name="weeklysplit",
            constraint=models.UniqueConstraint(
                fields=("owner", "weekday"), name="routines_unique_weekday_per_owner"
            ),
        ),
    ]

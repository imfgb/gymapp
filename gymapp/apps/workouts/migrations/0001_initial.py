"""Initial schema for `workouts`. Depends on users, exercises, routines."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exercises", "0001_initial"),
        ("routines", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkoutSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("in_progress", "In progress"),
                            ("finished", "Finished"),
                            ("abandoned", "Abandoned"),
                        ],
                        default="in_progress",
                        max_length=12,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="workouts_workoutsession_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_routine_day",
                    models.ForeignKey(
                        blank=True,
                        help_text="NULL = ad-hoc session not tied to a planned routine day.",
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="sessions",
                        to="routines.routineday",
                    ),
                ),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="ExerciseLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("ordering", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=200)),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="session_logs",
                        to="exercises.exercise",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="exercise_logs",
                        to="workouts.workoutsession",
                    ),
                ),
            ],
            options={"ordering": ["session", "ordering", "id"]},
        ),
        migrations.CreateModel(
            name="SetLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("ordering", models.PositiveSmallIntegerField(default=0)),
                (
                    "weight_kg",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=5, null=True
                    ),
                ),
                ("reps", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "rpe",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=3, null=True
                    ),
                ),
                ("is_warmup", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "exercise_log",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=models.deletion.CASCADE,
                        related_name="set_logs",
                        to="workouts.exerciselog",
                    ),
                ),
            ],
            options={"ordering": ["exercise_log", "ordering", "id"]},
        ),
    ]

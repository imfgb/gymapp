"""Initial schema for `prs`. Depends on users, exercises, workouts."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exercises", "0001_initial"),
        ("workouts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("weight_kg", models.DecimalField(decimal_places=2, max_digits=5)),
                ("reps", models.PositiveSmallIntegerField()),
                ("achieved_at", models.DateTimeField(db_index=True)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("auto", "Auto-detected"),
                            ("manual", "Manually entered"),
                        ],
                        default="auto",
                        max_length=8,
                    ),
                ),
                (
                    "exercise",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="personal_records",
                        to="exercises.exercise",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="prs_personalrecord_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_set",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "The SetLog that created/last-updated this PR. "
                            "NULL for manual entries."
                        ),
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="became_prs",
                        to="workouts.setlog",
                    ),
                ),
            ],
            options={"ordering": ["exercise", "reps"]},
        ),
        migrations.AddConstraint(
            model_name="personalrecord",
            constraint=models.UniqueConstraint(
                fields=("owner", "exercise", "reps"),
                name="prs_unique_per_owner_exercise_reps",
            ),
        ),
    ]

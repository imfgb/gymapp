"""Initial schema for `exercises`.

Hand-written for reviewability. After this lands, regenerate via
`python manage.py makemigrations exercises --dry-run` to verify the model
state matches; any drift means a hand-edit slipped vs. the auto output.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Equipment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=80)),
            ],
            options={
                "ordering": ["name"],
                "verbose_name_plural": "Equipment",
            },
        ),
        migrations.CreateModel(
            name="MuscleGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=80)),
                (
                    "region",
                    models.CharField(
                        choices=[
                            ("chest", "Chest"),
                            ("back", "Back"),
                            ("shoulders", "Shoulders"),
                            ("arms", "Arms"),
                            ("legs", "Legs"),
                            ("core", "Core"),
                        ],
                        max_length=20,
                    ),
                ),
            ],
            options={"ordering": ["region", "name"]},
        ),
        migrations.CreateModel(
            name="Exercise",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("slug", models.SlugField(max_length=80)),
                ("name", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[("compound", "Compound"), ("isolation", "Isolation")],
                        default="compound",
                        max_length=12,
                    ),
                ),
                ("unilateral", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "equipment",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=models.deletion.PROTECT,
                        related_name="exercises",
                        to="exercises.equipment",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "NULL = global (seeded). Otherwise the user who created "
                            "this custom exercise."
                        ),
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        related_name="custom_exercises",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "primary_muscles",
                    models.ManyToManyField(related_name="primary_for", to="exercises.musclegroup"),
                ),
                (
                    "secondary_muscles",
                    models.ManyToManyField(
                        blank=True, related_name="secondary_for", to="exercises.musclegroup"
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ExerciseAlternative",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=200)),
                (
                    "from_exercise",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="alternative_links_from",
                        to="exercises.exercise",
                    ),
                ),
                (
                    "to_exercise",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="alternative_links_to",
                        to="exercises.exercise",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="exercise",
            name="alternatives",
            field=models.ManyToManyField(
                blank=True,
                related_name="alternates_of",
                through="exercises.ExerciseAlternative",
                through_fields=("from_exercise", "to_exercise"),
                to="exercises.exercise",
            ),
        ),
        migrations.AddConstraint(
            model_name="exercise",
            constraint=models.UniqueConstraint(
                fields=("owner", "slug"), name="exercises_unique_slug_per_owner"
            ),
        ),
        migrations.AddConstraint(
            model_name="exercisealternative",
            constraint=models.UniqueConstraint(
                fields=("from_exercise", "to_exercise"),
                name="exercises_unique_alternative_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="exercisealternative",
            constraint=models.CheckConstraint(
                check=models.Q(("from_exercise", models.F("to_exercise")), _negated=True),
                name="exercises_alternative_not_self",
            ),
        ),
    ]

"""Initial schema for `metrics`."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMetricSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("measured_at", models.DateTimeField(db_index=True)),
                ("weight_kg", models.DecimalField(decimal_places=2, max_digits=5)),
                (
                    "body_fat_pct",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=4, null=True
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=200)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="metrics_usermetricsnapshot_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-measured_at"]},
        ),
    ]

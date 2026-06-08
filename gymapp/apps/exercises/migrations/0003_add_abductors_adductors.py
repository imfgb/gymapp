"""Add the hip Abductors + Adductors primary muscle groups (bug #6).

The original seed (0002) had no abductors/adductors, so users creating a custom
exercise couldn't tag the abductor/adductor machines. This adds them to
already-migrated databases (fresh installs get them from the updated YAML via
0002). Idempotent get_or_create; reverse is a no-op so user FKs don't orphan
(consistent with 0002 / ADR-024).
"""

from django.db import migrations

_GROUPS = [
    ("abductors", "Abductors"),
    ("adductors", "Adductors"),
]


def forwards(apps, schema_editor):
    MuscleGroup = apps.get_model("exercises", "MuscleGroup")
    for slug, name in _GROUPS:
        MuscleGroup.objects.get_or_create(
            slug=slug, defaults={"name": name, "region": "legs"}
        )


def backwards(apps, schema_editor):
    # Intentional no-op — keep seeded rows so user FKs to them don't orphan.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0002_seed_catalog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

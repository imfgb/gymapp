"""Data migration: load `seeds/exercises.yaml` into the catalogue.

Idempotent and re-runnable. Forward = upsert. Reverse = no-op (we keep seeded
rows even on reverse so user FKs to them don't orphan; if a true rollback is
needed, do it via fixtures/management command).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from gymapp.services.exercise_library.loader import apply_seed

    apply_seed(apps)


def backwards(apps, schema_editor):
    # Intentional no-op. Removing seeded rows would orphan user FKs.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exercises", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

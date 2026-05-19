"""Initial migration for `users`. MUST land before any other app's migrations
because every other app's FKs to AUTH_USER_MODEL depend on the User table
existing.

Hand-written rather than generated so the scaffold is reviewable in one read.
Re-generate via `python manage.py makemigrations users` once Django is
installed if you change the model.
"""
import django.utils.timezone
from django.db import migrations, models

import gymapp.apps.users.managers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates that this user has all permissions without "
                            "explicitly assigning them."
                        ),
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(blank=True, max_length=150, verbose_name="first name"),
                ),
                (
                    "last_name",
                    models.CharField(blank=True, max_length=150, verbose_name="last name"),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Designates whether this user should be treated as active. "
                            "Unselect this instead of deleting accounts."
                        ),
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="email address")),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "The groups this user belongs to. A user will get all "
                            "permissions granted to each of their groups."
                        ),
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
            },
            managers=[
                ("objects", gymapp.apps.users.managers.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("height_cm", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                (
                    "training_style",
                    models.CharField(
                        choices=[
                            ("bodybuilding", "Bodybuilding"),
                            ("powerlifting", "Powerlifting"),
                            ("powerbuilding", "Powerbuilding"),
                        ],
                        default="powerbuilding",
                        max_length=20,
                    ),
                ),
                (
                    "training_goal",
                    models.CharField(
                        choices=[
                            ("hypertrophy", "Hypertrophy"),
                            ("strength", "Strength"),
                            ("recomposition", "Recomposition"),
                            ("cut", "Cut"),
                            ("bulk", "Bulk"),
                            ("maintain", "Maintain"),
                        ],
                        default="hypertrophy",
                        max_length=20,
                    ),
                ),
                ("default_rest_seconds", models.PositiveSmallIntegerField(default=120)),
                ("must_change_password", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="profile",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Profile",
                "verbose_name_plural": "Profiles",
            },
        ),
    ]

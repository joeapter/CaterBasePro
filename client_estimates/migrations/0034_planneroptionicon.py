from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0033_alter_xpenzmobiletoken_options_estimateplannerentry_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannerOptionIcon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "section",
                    models.CharField(
                        choices=[
                            ("DECOR", "Decor"),
                            ("RENTALS", "Rentals"),
                            ("ORDERS", "Orders"),
                            ("SPECIAL_REQUESTS", "Special Requests"),
                            ("PRINTING", "Printing"),
                            ("STAFFING", "Staffing"),
                        ],
                        default="DECOR",
                        max_length=30,
                    ),
                ),
                ("group_code", models.CharField(blank=True, max_length=80)),
                ("item_code", models.CharField(blank=True, max_length=80)),
                (
                    "icon_key",
                    models.CharField(
                        choices=[
                            ("circle", "Circle (placeholder)"),
                            ("palette", "Palette"),
                            ("armchair", "Armchair"),
                            ("clipboard", "Clipboard"),
                            ("printer", "Printer"),
                            ("users", "Users"),
                            ("file", "File"),
                            ("sparkles", "Sparkles"),
                            ("table", "Table"),
                            ("package", "Package"),
                        ],
                        default="circle",
                        max_length=40,
                    ),
                ),
                ("is_manual_override", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "caterer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="planner_option_icons",
                        to="client_estimates.catereraccount",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="planner_option_icons_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Planner option icon",
                "verbose_name_plural": "Planner option icons",
                "ordering": ["section", "group_code", "item_code"],
                "unique_together": {("caterer", "section", "group_code", "item_code")},
            },
        ),
    ]


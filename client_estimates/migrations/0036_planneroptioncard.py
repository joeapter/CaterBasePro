from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0035_plannerfieldcard"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannerOptionCard",
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
                ("item_code", models.CharField(max_length=80)),
                ("item_label", models.CharField(max_length=120)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "caterer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="planner_option_cards",
                        to="client_estimates.catereraccount",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="planner_option_cards_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Planner option card",
                "verbose_name_plural": "Planner option cards",
                "ordering": ["section", "group_code", "sort_order", "item_label", "item_code"],
                "unique_together": {("caterer", "section", "group_code", "item_code")},
            },
        ),
    ]

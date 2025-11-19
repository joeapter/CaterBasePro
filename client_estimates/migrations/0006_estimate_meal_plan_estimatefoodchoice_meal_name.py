from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0005_remove_estimate_deposit_30_percent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimate",
            name="meal_plan",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of meal names (e.g. Friday Dinner, Shabbos Lunch) used to organize menu selections.",
            ),
        ),
        migrations.AddField(
            model_name="estimatefoodchoice",
            name="meal_name",
            field=models.CharField(
                blank=True,
                help_text="Optional meal label (e.g. Friday Dinner) for multi-meal estimates.",
                max_length=100,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="estimatefoodchoice",
            unique_together={("estimate", "menu_item", "meal_name")},
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0015_estimate_exchange_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimate",
            name="meal_guest_overrides",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Optional override per meal for adult/kid counts.",
            ),
        ),
    ]

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0014_estimate_guest_count_kids"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimate",
            name="exchange_rate",
            field=models.DecimalField(
                default=Decimal("1.00"),
                max_digits=10,
                decimal_places=4,
                help_text="Optional manual FX rate to convert totals into the selected currency.",
            ),
        ),
    ]


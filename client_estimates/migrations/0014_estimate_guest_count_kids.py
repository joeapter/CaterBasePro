from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("client_estimates", "0013_catereraccount_trial_expires_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimate",
            name="guest_count_kids",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Kids count for separate pricing when using kids menu category.",
            ),
        ),
    ]


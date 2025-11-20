from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('client_estimates', '0009_catereraccount_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='estimate',
            name='manual_meal_totals',
            field=models.JSONField(blank=True, default=dict, help_text='Stores manual per-meal price overrides.'),
        ),
    ]

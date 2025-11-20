from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from client_estimates.models import (
    CatererAccount,
    Estimate,
    EstimateExtraItem,
    EstimateFoodChoice,
    ExtraItem,
    MenuCategory,
    MenuItem,
    MenuTemplate,
)


class Command(BaseCommand):
    help = "Export a caterer owner's user record and related data as a JSON fixture."

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            help="Django username that owns the CatererAccount you want to export.",
        )
        parser.add_argument(
            "-o",
            "--output",
            help="Optional file path for the JSON fixture. Prints to stdout if omitted.",
        )

    def handle(self, username: str, output: str | None = None, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No user found with username '{username}'") from exc

        caterers = list(CatererAccount.objects.filter(owner=user))
        if not caterers:
            raise CommandError(
                f"User '{username}' does not own any CatererAccount records."
            )
        caterer_ids = [c.pk for c in caterers]

        querysets = [
            user_model.objects.filter(pk=user.pk),
            Group.objects.filter(user=user),
            Permission.objects.filter(user=user),
            CatererAccount.objects.filter(pk__in=caterer_ids),
            MenuCategory.objects.filter(caterer_id__in=caterer_ids),
            MenuItem.objects.filter(caterer_id__in=caterer_ids),
            MenuTemplate.objects.filter(caterer_id__in=caterer_ids),
            ExtraItem.objects.filter(caterer_id__in=caterer_ids),
            Estimate.objects.filter(caterer_id__in=caterer_ids),
            EstimateFoodChoice.objects.filter(estimate__caterer_id__in=caterer_ids),
            EstimateExtraItem.objects.filter(estimate__caterer_id__in=caterer_ids),
        ]

        objects = []
        for qs in querysets:
            objects.extend(list(qs))

        if not objects:
            raise CommandError("Nothing to export.")

        payload = serializers.serialize(
            "json",
            objects,
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
            indent=2,
        )

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exported {len(objects)} objects for '{username}' to {output_path}"
                )
            )
        else:
            self.stdout.write(payload)

import csv
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone

from client_estimates.models import CatererAccount, ShoppingList, ShoppingListItem
from client_estimates.views import _infer_shopping_category

from .models import ShoppingListBulkImport


class ShoppingListBulkImportForm(forms.Form):
    caterer = forms.ModelChoiceField(
        queryset=CatererAccount.objects.none(),
        label="Caterer",
    )
    shopping_list = forms.ModelChoiceField(
        queryset=ShoppingList.objects.none(),
        required=False,
        label="Add to existing shopping list",
        help_text="Optional. If blank, a new list will be created.",
    )
    new_list_title = forms.CharField(
        required=False,
        label="New shopping list title",
        help_text="Used only when no existing list is selected.",
        max_length=200,
    )
    default_item_type = forms.CharField(
        required=False,
        label="Default item type",
        max_length=120,
    )
    default_item_unit = forms.CharField(
        required=False,
        label="Default unit",
        max_length=60,
        help_text="Example: Kg / Pieces / Cans",
    )
    default_quantity = forms.DecimalField(
        required=False,
        label="Default quantity",
        initial=Decimal("1.00"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=10,
    )
    items_text = forms.CharField(
        label="Bulk paste items",
        widget=forms.Textarea(attrs={"rows": 18, "placeholder": "One item per line"}),
        help_text=(
            "Paste one item per line. Optional line format: "
            "Item | Type | Quantity | Unit"
        ),
    )


@admin.register(ShoppingListBulkImport)
class ShoppingListBulkImportAdmin(admin.ModelAdmin):
    list_display = ("title", "caterer", "updated_at", "created_at")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "bulk-import/",
                self.admin_site.admin_view(self.bulk_import_view),
                name=self._admin_url_name("bulk_import"),
            )
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse(f"admin:{self._admin_url_name('bulk_import')}"))

    def _admin_url_name(self, suffix):
        opts = self.model._meta
        return f"{opts.app_label}_{opts.model_name}_{suffix}"

    def _allowed_caterers(self, request):
        qs = CatererAccount.objects.all()
        if request.user.is_superuser:
            return qs
        return qs.filter(owner=request.user)

    def _allowed_shopping_lists(self, request, caterer=None):
        qs = ShoppingList.objects.select_related("caterer")
        if request.user.is_superuser:
            if caterer:
                qs = qs.filter(caterer=caterer)
            return qs.order_by("-updated_at", "-created_at")
        qs = qs.filter(caterer__owner=request.user)
        if caterer:
            qs = qs.filter(caterer=caterer)
        return qs.order_by("-updated_at", "-created_at")

    @staticmethod
    def _normalize(value):
        return " ".join((value or "").split()).strip()

    @staticmethod
    def _parse_quantity(raw_value):
        cleaned = str(raw_value or "").strip()
        if not cleaned:
            return None
        try:
            quantity = Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
        if quantity <= Decimal("0.00"):
            return None
        return quantity.quantize(Decimal("0.01"))

    def _parse_bulk_line(self, line):
        cleaned = self._normalize(line)
        if not cleaned:
            return {"item_name": "", "item_type": "", "quantity": None, "item_unit": ""}

        if "|" in cleaned:
            parts = [self._normalize(part) for part in cleaned.split("|")]
        elif "," in cleaned:
            parts = [self._normalize(part) for part in next(csv.reader([cleaned], skipinitialspace=True))]
        else:
            parts = [cleaned]

        item_name = self._normalize(parts[0] if len(parts) > 0 else "")
        item_type = self._normalize(parts[1] if len(parts) > 1 else "")
        quantity = self._parse_quantity(parts[2] if len(parts) > 2 else "")
        item_unit = self._normalize(parts[3] if len(parts) > 3 else "")
        return {
            "item_name": item_name,
            "item_type": item_type,
            "quantity": quantity,
            "item_unit": item_unit,
        }

    def bulk_import_view(self, request):
        allowed_caterers = self._allowed_caterers(request).order_by("name")
        if not request.user.is_superuser and not allowed_caterers.exists():
            raise PermissionDenied("No caterer account is available for this user.")

        form = (
            ShoppingListBulkImportForm(request.POST)
            if request.method == "POST"
            else ShoppingListBulkImportForm()
        )
        form.fields["caterer"].queryset = allowed_caterers

        selected_caterer = None
        if request.method == "POST":
            raw_caterer_id = (request.POST.get("caterer") or "").strip()
        else:
            raw_caterer_id = (request.GET.get("caterer") or "").strip()
        if raw_caterer_id.isdigit():
            selected_caterer = allowed_caterers.filter(pk=int(raw_caterer_id)).first()
        if not selected_caterer and allowed_caterers.count() == 1:
            selected_caterer = allowed_caterers.first()
            form.fields["caterer"].initial = selected_caterer

        shopping_list_qs = self._allowed_shopping_lists(request, selected_caterer)
        form.fields["shopping_list"].queryset = shopping_list_qs

        if request.method == "GET":
            raw_shopping_list_id = (request.GET.get("shopping_list") or "").strip()
            if raw_shopping_list_id.isdigit():
                selected_list = shopping_list_qs.filter(pk=int(raw_shopping_list_id)).first()
                if selected_list:
                    form.fields["shopping_list"].initial = selected_list

        if request.method == "POST" and form.is_valid():
            caterer = form.cleaned_data["caterer"]
            shopping_list = form.cleaned_data["shopping_list"]
            if shopping_list and shopping_list.caterer_id != caterer.id:
                form.add_error("shopping_list", "Selected list does not belong to this caterer.")
            else:
                new_list_title = self._normalize(form.cleaned_data.get("new_list_title") or "")
                raw_lines = (form.cleaned_data.get("items_text") or "").splitlines()
                non_empty_lines = [line for line in raw_lines if self._normalize(line)]
                if not non_empty_lines:
                    form.add_error("items_text", "Paste at least one shopping list item.")
                else:
                    if not shopping_list:
                        if not new_list_title:
                            stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
                            new_list_title = f"Bulk Import {stamp}"
                        shopping_list = ShoppingList.objects.create(
                            caterer=caterer,
                            title=new_list_title,
                            created_by=request.user,
                        )

                    default_item_type = self._normalize(form.cleaned_data.get("default_item_type") or "")
                    default_item_unit = self._normalize(form.cleaned_data.get("default_item_unit") or "")
                    default_quantity = (
                        form.cleaned_data.get("default_quantity")
                        or Decimal("1.00")
                    ).quantize(Decimal("0.01"))

                    execution_started_by_other = bool(
                        shopping_list.execution_started_at
                        and shopping_list.execution_started_by_id
                        and shopping_list.execution_started_by_id != request.user.id
                    )

                    created_count = 0
                    merged_count = 0
                    skipped_count = 0
                    for raw_line in raw_lines:
                        parsed = self._parse_bulk_line(raw_line)
                        item_name = parsed["item_name"]
                        if not item_name:
                            continue

                        item_type = parsed["item_type"] or default_item_type
                        item_unit = parsed["item_unit"] or default_item_unit
                        quantity = parsed["quantity"] or default_quantity
                        category = _infer_shopping_category(item_name)

                        existing = ShoppingListItem.objects.filter(
                            shopping_list=shopping_list,
                            is_completed=False,
                            item_name__iexact=item_name,
                            item_type__iexact=item_type,
                            item_unit__iexact=item_unit,
                        ).first()
                        if existing:
                            existing.quantity = (existing.quantity or Decimal("0.00")) + quantity
                            existing.category = category
                            if execution_started_by_other:
                                existing.collaboration_note = "COMBINED"
                            existing.save(
                                update_fields=["quantity", "category", "collaboration_note", "updated_at"]
                            )
                            merged_count += 1
                            continue

                        collaboration_note = "ADDED" if execution_started_by_other else ""
                        ShoppingListItem.objects.create(
                            shopping_list=shopping_list,
                            item_name=item_name,
                            item_type=item_type,
                            item_unit=item_unit,
                            quantity=quantity,
                            category=category,
                            collaboration_note=collaboration_note,
                            created_by=request.user,
                        )
                        created_count += 1

                    if created_count == 0 and merged_count == 0:
                        skipped_count = len(non_empty_lines)

                    ShoppingList.objects.filter(pk=shopping_list.pk).update(updated_at=timezone.now())
                    self.message_user(
                        request,
                        (
                            f"Bulk import complete for '{shopping_list.title}': "
                            f"{created_count} created, {merged_count} merged, {skipped_count} skipped."
                        ),
                        level=messages.SUCCESS,
                    )
                    target = reverse(f"admin:{self._admin_url_name('bulk_import')}")
                    return redirect(
                        f"{target}?caterer={caterer.id}&shopping_list={shopping_list.id}"
                    )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Shopping List Bulk Paste Import",
            "form": form,
        }
        return render(request, "admin/shopping_list_tool/bulk_import.html", context)

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj=obj)

    def has_add_permission(self, request):
        return self.has_view_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

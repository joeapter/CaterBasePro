from decimal import Decimal, InvalidOperation
import csv
from collections import defaultdict
import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.utils import flatten_fieldsets, unquote
from django.core.exceptions import PermissionDenied
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.forms.formsets import all_valid
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from .models import (
    CatererAccount,
    MenuCategory,
    MenuItem,
    ExtraItem,
    Estimate,
    EstimateFoodChoice,
    EstimateExtraItem,
    MenuTemplate,
    ClientInquiry,
    ClientProfile,
    CatererTask,
    TastingAppointment,
    TrialRequest,
)

# ==========================
# 🔐 PERMISSIONS & SCOPING
# ==========================
def limit_to_user_caterer(queryset, request):
    if request.user.is_superuser:
        return queryset
    return queryset.filter(caterer__owner=request.user)

def user_can_access_caterer(request, obj=None):
    if request.user.is_superuser:
        return True
    if obj is None:
        return False
    return obj.owner == request.user


def parse_meal_plan(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        names = raw_value
    else:
        names = [line.strip() for line in str(raw_value).replace(",", "\n").splitlines()]
    return [name for name in names if name]

# ==========================
# CATERER ACCOUNT ADMIN
# ==========================
@admin.register(CatererAccount)
class CatererAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "default_currency")
    search_fields = ("name",)
    readonly_fields = ("slug",)
    base_fieldsets = (
        (
            "Company Basics",
            {
                "fields": (
                    "name",
                    "owner",
                    "primary_contact_name",
                    "default_currency",
                    "slug",
                    "company_phone",
                    "company_email",
                    "company_address",
                )
            },
        ),
        (
            "Branding & Document Style",
            {
                "fields": (
                    "brand_logo",
                    "brand_primary_color",
                    "brand_accent_color",
                    "document_background",
                    "document_font_family",
                    "document_surface_style",
                    "default_payment_terms",
                )
            },
        ),
        (
            "Dashboard Messaging",
            {
                "fields": (
                    "dashboard_banner_message",
                    "dashboard_banner_start",
                    "dashboard_banner_end",
                )
            },
        ),
        (
            "Banking & Payment",
            {
                "fields": (
                    "bank_details",
                    "estimate_number_counter",
                )
            },
        ),
        (
            "Pricing Defaults",
            {
                "fields": (
                    "default_food_markup",
                    "staff_hourly_rate",
                    "staff_tip_per_waiter",
                    "real_dishes_price_per_person",
                    "real_dishes_flat_fee",
                )
            },
        ),
    )
    fieldsets = base_fieldsets

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(self.base_fieldsets)
        if request.user.is_superuser:
            return fieldsets
        return [fs for fs in fieldsets if fs[0] != "Dashboard Messaging"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(owner=request.user)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or user_can_access_caterer(request, obj)

# ==========================
# MENU CATEGORY ADMIN
# ==========================
@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "caterer", "sort_order")
    list_editable = ("sort_order",)
    list_filter = ("caterer",)
    ordering = ["sort_order"]

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form


@admin.register(ClientInquiry)
class ClientInquiryAdmin(admin.ModelAdmin):
    list_display = ("contact_name", "caterer", "status", "event_date", "created_at")
    list_filter = ("status", "caterer")
    search_fields = ("contact_name", "company_name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "caterer", "email", "phone", "birthday")
    search_fields = ("name", "email", "phone")
    list_filter = ("caterer",)

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form


@admin.register(CatererTask)
class CatererTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "caterer", "due_date", "completed")
    list_filter = ("completed", "caterer")
    search_fields = ("title", "description")

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
            if "related_inquiry" in form.base_fields:
                form.base_fields["related_inquiry"].queryset = ClientInquiry.objects.filter(
                    caterer__owner=request.user
                )
        return form

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

# ==========================
# MENU ITEM ADMIN + CSV UPLOAD
# ==========================
class MenuUploadForm(forms.Form):
    csv_file = forms.FileField()

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "caterer", "category", "cost_per_serving", "markup", "is_active")
    list_filter = ("caterer", "category", "is_active")
    search_fields = ("name",)
    change_list_template = "admin/menu_upload.html"

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form


@admin.register(TastingAppointment)
class TastingAppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "start_at",
        "appointment_type",
        "status",
        "caterer",
        "client_name",
        "estimate",
    )
    list_filter = ("appointment_type", "status", "caterer")
    search_fields = ("title", "client_name", "client_email", "client_phone", "notes")
    readonly_fields = ("created_at",)
    ordering = ("start_at",)

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and "caterer" in form.base_fields:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
            form.base_fields["estimate"].queryset = Estimate.objects.filter(caterer__owner=request.user)
        return form

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        estimate_id = request.GET.get("estimate")
        if estimate_id:
            try:
                estimate = Estimate.objects.select_related("caterer", "caterer__owner").get(pk=estimate_id)
            except Estimate.DoesNotExist:
                return initial
            if request.user.is_superuser or estimate.caterer.owner == request.user:
                initial.setdefault("caterer", estimate.caterer)
                initial.setdefault("estimate", estimate)
                initial.setdefault("client_name", estimate.customer_name)
                initial.setdefault("client_email", estimate.customer_email)
                initial.setdefault("client_phone", estimate.customer_phone)
                initial.setdefault("title", f"Tasting for {estimate.customer_name}")
        return initial

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return obj.caterer.owner == request.user

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.caterer.owner == request.user

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.caterer.owner == request.user

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

    def save_model(self, request, obj, form, change):
        if obj.estimate:
            obj.caterer = obj.estimate.caterer
            if not obj.client_name:
                obj.client_name = obj.estimate.customer_name
            if not obj.client_email:
                obj.client_email = obj.estimate.customer_email
            if not obj.client_phone:
                obj.client_phone = obj.estimate.customer_phone
        super().save_model(request, obj, form, change)


@admin.register(TrialRequest)
class TrialRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "created_at")
    search_fields = ("name", "email", "phone", "notes")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("upload-csv/", self.admin_site.admin_view(self.upload_csv), name="menu-upload-csv"),
            path("download-template/", self.admin_site.admin_view(self.download_template), name="menu-download-template"),
        ]
        return custom + urls

    def upload_csv(self, request):
        if request.method == "POST":
            form = MenuUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data["csv_file"]
                raw_bytes = file.read()
                try:
                    decoded = raw_bytes.decode("utf-8-sig").splitlines()
                except UnicodeDecodeError:
                    decoded = raw_bytes.decode("latin-1").splitlines()
                reader = csv.DictReader(decoded)

                caterer = CatererAccount.objects.filter(owner=request.user).first()
                if not caterer:
                    self.message_user(request, "No caterer linked to your account.", level=messages.ERROR)
                    return redirect("..")

                created_count = 0
                for row in reader:
                    item_type = row["item_type"].strip().lower()
                    category_name = row["category"].strip().title()
                    name = row["name"].strip()

                    category, _ = MenuCategory.objects.get_or_create(
                        caterer=caterer, name=category_name
                    )

                    def parse_decimal(value, default="0.0"):
                        try:
                            return Decimal(value.strip()) if value and str(value).strip() else Decimal(default)
                        except (InvalidOperation, AttributeError):
                            return Decimal(default)

                    cost = parse_decimal(row.get("cost_per_serving"), "0.0")
                    markup = parse_decimal(row.get("markup"), str(caterer.default_food_markup))
                    if markup == Decimal("0.0"):
                        markup = caterer.default_food_markup
                    servings = parse_decimal(row.get("default_servings_per_person"), "1.0")
                    is_active = str(row.get("is_active", "true")).lower() == "true"

                    if item_type == "food":
                        MenuItem.objects.create(
                            caterer=caterer,
                            category=category,
                            name=name,
                            description=row.get("description", ""),
                            cost_per_serving=cost,
                            markup=markup,
                            default_servings_per_person=servings,
                            is_active=is_active,
                        )
                    else:
                        ExtraItem.objects.create(
                            caterer=caterer,
                            name=name,
                            category="RENTAL",
                            charge_type="PER_EVENT",
                            price=(cost * markup).quantize(Decimal("0.01")),
                            cost=cost,
                            is_active=is_active,
                        )
                    created_count += 1

                self.message_user(
                    request,
                    f"Successfully imported {created_count} items",
                    level=messages.SUCCESS,
                )
                return redirect("..")

        else:
            form = MenuUploadForm()

        return render(
            request,
            "admin/menu_upload_form.html",
            {"form": form, "title": "Upload Menu Items via CSV"},
        )

    def download_template(self, request):
        headers = [
            "item_type",
            "category",
            "name",
            "description",
            "cost_per_serving",
            "markup",
            "default_servings_per_person",
            "is_active",
        ]
        sample_rows = [
            ["Food", "Starters", "Smoked Salmon Bites", "Mini bagels with lox", "12.50", "3.0", "1.0", "True"],
            ["Food", "Mains", "Steak Strip", "Grilled steak strips", "28.00", "", "1.0", "True"],
            ["Extra", "Rental", "Projector", "", "400", "3.0", "1.0", "True"],
        ]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="menu_template.csv"'
        writer = csv.writer(response)
        writer.writerow(headers)
        for row in sample_rows:
            writer.writerow(row)
        return response

# ==========================
# EXTRA ITEM ADMIN
# ==========================
@admin.register(ExtraItem)
class ExtraItemAdmin(admin.ModelAdmin):
    list_display = ("name", "caterer", "category", "charge_type", "price", "is_active")
    list_filter = ("caterer", "category", "charge_type", "is_active")
    search_fields = ("name",)

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form

# ==========================
# MENU TEMPLATE ADMIN (optional/simple)
# ==========================
@admin.register(MenuTemplate)
class MenuTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "caterer", "created_at")
    filter_horizontal = ("items",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(caterer__owner=request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        return form

# ==========================
# ESTIMATE ADMIN – CHECKLIST + TEMPLATES
# ==========================
class EstimateAdminForm(forms.ModelForm):
    meal_plan_input = forms.CharField(
        required=False,
        label="Meals being quoted",
        help_text="Enter one meal per line (e.g. Friday Night Dinner). Leave blank for a single meal.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    use_template = forms.ModelChoiceField(
        queryset=MenuTemplate.objects.none(),
        required=False,
        label="Apply menu template",
        help_text="If you pick a template and save, items from that template will be applied.",
    )
    save_as_template = forms.CharField(
        required=False,
        label="Save current selection as a new template (name)",
    )
    manual_meal_totals_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Estimate
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        # custom hook to get request
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Determine caterer
        caterer = None
        if self.instance and self.instance.pk and self.instance.caterer_id:
            caterer = self.instance.caterer
        elif self.request:
            caterer = (
                CatererAccount.objects.filter(owner=self.request.user).first()
            )
            if caterer and not self.instance.pk:
                self.fields["caterer"].initial = caterer
                if "payment_terms" in self.fields and not self.fields["payment_terms"].initial:
                    self.fields["payment_terms"].initial = caterer.default_payment_terms
                if (
                    "payment_instructions" in self.fields
                    and not self.fields["payment_instructions"].initial
                    and caterer.bank_details
                ):
                    self.fields["payment_instructions"].initial = caterer.bank_details
                if (
                    "payment_method" in self.fields
                    and not self.fields["payment_method"].initial
                ):
                    default_method = "BANK_TRANSFER" if caterer.bank_details else "CASH"
                    self.fields["payment_method"].initial = default_method

        # Limit use_template queryset
        if caterer:
            self.fields["use_template"].queryset = MenuTemplate.objects.filter(
                caterer=caterer
            )
        else:
            self.fields["use_template"].queryset = MenuTemplate.objects.none()

        # Determine meals
        raw_meal_input = self.data.get("meal_plan_input") if self.data else None
        if raw_meal_input:
            meal_names = parse_meal_plan(raw_meal_input)
        elif self.instance and self.instance.meal_plan:
            meal_names = self.instance.get_meal_plan()
        else:
            meal_names = ["Signature Menu"]
        self.meal_names = meal_names
        self.fields["meal_plan_input"].initial = "\n".join(meal_names)
        if not self.data:
            self.fields["manual_meal_totals_json"].initial = json.dumps(
                self.instance.manual_meal_totals or {}
            )

        # Build dynamic item checklist
        self.menu_items = []
        if caterer:
            menu_qs = (
                MenuItem.objects.filter(
                    caterer=caterer,
                    is_active=True,
                )
                .select_related("category")
                .order_by("category__sort_order", "category__name", "name")
            )
            existing_choices = {}
            if self.instance and self.instance.pk:
                for ch in self.instance.food_choices.all():
                    key = (ch.menu_item_id, ch.meal_name or self.instance.default_meal_name())
                    existing_choices[key] = ch

            for item in menu_qs:
                self.menu_items.append(item)
                for idx, meal_name in enumerate(self.meal_names):
                    include_name = f"include_item_{item.id}_meal_{idx}"
                    servings_name = f"servings_item_{item.id}_meal_{idx}"

                    existing_key = (item.id, meal_name)
                    included_initial = existing_key in existing_choices
                    if included_initial and existing_choices[existing_key].servings_per_person:
                        servings_initial = existing_choices[existing_key].servings_per_person
                    else:
                        servings_initial = item.default_servings_per_person

                    self.fields[include_name] = forms.BooleanField(
                        label=f"{item.name} ({meal_name})",
                        required=False,
                        initial=included_initial,
                    )
                    self.fields[servings_name] = forms.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        required=False,
                        initial=servings_initial,
                        label="Servings per person",
                        widget=forms.HiddenInput(),
                    )
        else:
            self.menu_items = []

        # Decor / add-on extras
        self.decor_items = []
        self.addon_items = []
        self.extra_items = []
        if caterer:
            extra_qs = (
                ExtraItem.objects.filter(
                    caterer=caterer,
                    is_active=True,
                )
                .order_by("category", "name")
            )
            existing_lines = {}
            if self.instance and self.instance.pk:
                for line in self.instance.extra_lines.all():
                    existing_lines[line.extra_item_id] = line

            for extra in extra_qs:
                include_name = f"include_extra_{extra.id}"
                quantity_name = f"quantity_extra_{extra.id}"
                override_name = f"override_extra_{extra.id}"

                existing_line = existing_lines.get(extra.id)
                included_initial = existing_line is not None
                quantity_initial = (
                    existing_line.quantity if existing_line else Decimal("1.00")
                )
                override_initial = (
                    existing_line.override_price if existing_line else None
                )

                self.fields[include_name] = forms.BooleanField(
                    label=f"{extra.name}",
                    required=False,
                    initial=included_initial,
                )
                self.fields[quantity_name] = forms.DecimalField(
                    max_digits=8,
                    decimal_places=2,
                    required=False,
                    initial=quantity_initial,
                    label="Quantity",
                    min_value=Decimal("0.00"),
                )
                self.fields[override_name] = forms.DecimalField(
                    max_digits=10,
                    decimal_places=2,
                    required=False,
                    initial=override_initial,
                    label="Override price",
                    help_text="Leave blank to use the catalog price.",
                )

                self.extra_items.append(extra)
                if extra.category in ("DECOR", "RENTAL"):
                    self.decor_items.append(extra)
                else:
                    self.addon_items.append(extra)


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    form = EstimateAdminForm
    change_form_template = "admin/estimate_change_form.html"

    list_display = (
        "estimate_number",
        "customer_name",
        "event_type",
        "event_date",
        "guest_count",
        "caterer",
        "grand_total",
        "is_invoice",
        "print_estimate_button",
        "workflow_button",
        "flat_print_button",
        "schedule_button",
    )
    list_filter = ("event_date", "caterer", "is_invoice")
    search_fields = ("customer_name", "event_type")

    fieldsets = (
        (
            "Customer & Event",
            {
                "classes": ("estimate-step", "estimate-step-1"),
                "fields": (
                    "caterer",
                    "estimate_number",
                    "currency",
                    "customer_name",
                    "customer_phone",
                    "customer_email",
                    "event_type",
                    "event_date",
                    "event_location",
                    "guest_count",
                    "guest_count_kids",
                    "exchange_rate",
                    "include_premium_plastic",
                    "include_premium_tablecloths",
                ),
            },
        ),
        (
            "Menu Templates",
            {
                "classes": ("estimate-step", "estimate-step-2"),
                "fields": (
                    "meal_plan_input",
                    "use_template",
                    "save_as_template",
                ),
            },
        ),
        (
            "Summary & Logistics",
            {
                "classes": ("estimate-step", "estimate-step-5"),
                "fields": (
                    "is_ala_carte",
                    "wants_real_dishes",
                    "real_dishes_price_per_person",
                    "real_dishes_flat_fee",
                    "staff_hours",
                    "extra_waiters",
                    "staff_hourly_rate",
                    "staff_tip_per_waiter",
                    "notes_internal",
                    "notes_for_customer",
                    "deposit_percentage",
                    "payment_terms",
                    "payment_method",
                    "payment_instructions",
                    "contract_terms",
                    "terms_acknowledged",
                    "signature_name",
                    "signature_title",
                    "signature_date",
                    "food_price_per_person",
                    "extras_total",
                    "staff_total",
                    "dishes_total",
                    "grand_total",
                    "deposit_amount",
                    "balance_due",
                    "created_at",
                    "updated_at",
                    "is_invoice",
                ),
            },
        ),
    )
    readonly_fields = (
        "food_price_per_person",
        "extras_total",
        "staff_total",
        "dishes_total",
        "grand_total",
        "deposit_amount",
        "balance_due",
        "created_at",
        "updated_at",
        "is_invoice",
        "estimate_number",
    )

    actions = ["delete_selected", "workflow_bulk_action"]

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

    def workflow_bulk_action(self, request, queryset):
        ids = list(queryset.values_list("pk", flat=True))
        if not ids:
            self.message_user(request, "Select at least one estimate to print workflows.", level=messages.WARNING)
            return
        url = reverse("admin:client_estimates_estimate_workflow_bulk")
        params = ",".join(str(i) for i in ids)
        return HttpResponseRedirect(f"{url}?ids={params}&print=1")

    workflow_bulk_action.short_description = "Print kitchen workflows"

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        inquiry_id = request.GET.get("client_inquiry")
        if inquiry_id:
            try:
                inquiry = ClientInquiry.objects.select_related("caterer", "caterer__owner").get(pk=inquiry_id)
            except ClientInquiry.DoesNotExist:
                pass
            else:
                if request.user.is_superuser or inquiry.caterer.owner == request.user:
                    initial.setdefault("caterer", inquiry.caterer)
                    initial.setdefault("customer_name", inquiry.contact_name)
                    initial.setdefault("customer_phone", inquiry.phone)
                    initial.setdefault("customer_email", inquiry.email)
                    initial.setdefault("event_type", inquiry.event_type)
                    if inquiry.event_date:
                        initial.setdefault("event_date", inquiry.event_date)
                    if inquiry.notes:
                        initial.setdefault("notes_internal", inquiry.notes)
        return initial

    def get_form(self, request, obj=None, **kwargs):
        """
        Inject `request` into the form so it can know which caterer/user.
        Also limit caterer choices to the current user's caterer.
        """
        base_form = self.form

        class FormWithRequest(base_form):
            def __init__(self2, *a, **kw):
                kw["request"] = request
                super().__init__(*a, **kw)

        kwargs["form"] = FormWithRequest
        form_class = super().get_form(request, obj, **kwargs)

        if not request.user.is_superuser and "caterer" in form_class.base_fields:
            form_class.base_fields["caterer"].queryset = CatererAccount.objects.filter(
                owner=request.user
            )

        return form_class

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.caterer.owner == request.user

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.caterer.owner == request.user

    def save_model(self, request, obj, form, change):
        """
        Save the Estimate, then build EstimateFoodChoice rows based on
        the checkbox selection and template usage. Also optionally save a new template.
        """
        is_new = obj.pk is None
        if is_new or not obj.estimate_number:
            counter = obj.caterer.estimate_number_counter or 1000
            obj.estimate_number = counter
            obj.caterer.estimate_number_counter = counter + 1
            obj.caterer.save(update_fields=["estimate_number_counter"])

        meal_names = parse_meal_plan(form.cleaned_data.get("meal_plan_input"))
        if not meal_names:
            meal_names = ["Signature Menu"]
        obj.meal_plan = meal_names

        overrides_raw = form.cleaned_data.get("manual_meal_totals_json")
        try:
            obj.manual_meal_totals = json.loads(overrides_raw) if overrides_raw else {}
        except json.JSONDecodeError:
            obj.manual_meal_totals = {}

        super().save_model(request, obj, form, change)

        menu_items = getattr(form, "menu_items", [])
        selected_entries = []

        # Collect explicit checkbox selections
        for item in menu_items:
            for idx, meal_name in enumerate(meal_names):
                include_name = f"include_item_{item.id}_meal_{idx}"
                servings_name = f"servings_item_{item.id}_meal_{idx}"
                if form.cleaned_data.get(include_name):
                    servings = form.cleaned_data.get(servings_name) or item.default_servings_per_person
                    selected_entries.append((item, meal_name, servings))

        # If a template was chosen and nothing selected manually, use template for primary meal
        use_template = form.cleaned_data.get("use_template")
        if use_template and not selected_entries:
            template_item_ids = list(use_template.items.values_list("id", flat=True))
            for mid in template_item_ids:
                try:
                    mi = next(m for m in menu_items if m.id == mid)
                except StopIteration:
                    mi = MenuItem.objects.get(id=mid)
                selected_entries.append((mi, meal_names[0], mi.default_servings_per_person))

        # Replace existing food choices
        EstimateFoodChoice.objects.filter(estimate=obj).delete()
        for item, meal_name, servings in selected_entries:
            EstimateFoodChoice.objects.create(
                estimate=obj,
                menu_item=item,
                included=True,
                servings_per_person=servings,
                meal_name=meal_name,
            )

        # Optionally save current selection as a new template
        template_name = form.cleaned_data.get("save_as_template")
        if template_name and selected_entries:
            caterer = obj.caterer
            tmpl, created = MenuTemplate.objects.get_or_create(
                caterer=caterer,
                name=template_name,
            )
            tmpl.items.set(MenuItem.objects.filter(id__in=[item.id for item, _, _ in selected_entries]))

        # Replace extra items based on wizard selections
        extra_items = getattr(form, "extra_items", [])
        if extra_items:
            EstimateExtraItem.objects.filter(estimate=obj).delete()
            for extra in extra_items:
                include_name = f"include_extra_{extra.id}"
                quantity_name = f"quantity_extra_{extra.id}"
                override_name = f"override_extra_{extra.id}"

                if not form.cleaned_data.get(include_name):
                    continue

                quantity = form.cleaned_data.get(quantity_name) or Decimal("1.00")
                override_price = form.cleaned_data.get(override_name)
                EstimateExtraItem.objects.create(
                    estimate=obj,
                    extra_item=extra,
                    quantity=quantity,
                    override_price=override_price,
                )
        # After rebuilding related rows, recalc totals now that selections exist
        obj.save()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:estimate_id>/print/",
                self.admin_site.admin_view(self.print_estimate),
                name="client_estimates_estimate_print",
            ),
            path(
                "<int:estimate_id>/print-flat/",
                self.admin_site.admin_view(self.print_estimate_flat),
                name="client_estimates_estimate_print_flat",
            ),
            path(
                "<int:estimate_id>/workflow/",
                self.admin_site.admin_view(self.workflow_view),
                name="client_estimates_estimate_workflow",
            ),
            path(
                "workflow/bulk/",
                self.admin_site.admin_view(self.workflow_bulk_view),
                name="client_estimates_estimate_workflow_bulk",
            ),
        ]
        return custom + urls

    def print_estimate_button(self, obj):
        url = reverse("admin:client_estimates_estimate_print", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">Print PDF</a>', url)

    print_estimate_button.short_description = "Download"

    def workflow_button(self, obj):
        url = reverse("admin:client_estimates_estimate_workflow", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">Workflow</a>', f"{url}?print=1")

    workflow_button.short_description = "Kitchen"

    def flat_print_button(self, obj):
        url = reverse("admin:client_estimates_estimate_print_flat", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">PP Flat Estimate</a>', url)

    flat_print_button.short_description = "PP Flat"

    def schedule_button(self, obj):
        url = reverse("admin:client_estimates_tastingappointment_add")
        return format_html(
            '<a class="button" href="{}?estimate={}">Schedule tasting/meeting</a>',
            url,
            obj.pk,
        )

    schedule_button.short_description = "Schedule"

    def print_estimate(self, request, estimate_id):
        estimate = Estimate.objects.select_related("caterer", "caterer__owner").get(pk=estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")

        extra_lines = (
            estimate.extra_lines.select_related("extra_item")
            .order_by("extra_item__category", "extra_item__name")
        )

        caterer = estimate.caterer
        staff_context = None
        if not estimate.is_ala_carte:
            waiters = estimate.total_waiter_count()
            staff_hours = estimate.staff_hours or Decimal("0.00")
            rate = estimate._get_staff_hourly_rate()
            tip = estimate._get_staff_tip_per_waiter()
            staff_pay = (rate * staff_hours * waiters).quantize(Decimal("0.01"))
            staff_tip = (tip * waiters).quantize(Decimal("0.01"))
            staff_context = {
                "waiters": waiters,
                "hours": staff_hours,
                "hourly_rate": rate,
                "labor_total": staff_pay,
                "tip_per_waiter": tip,
                "tip_total": staff_tip,
                "grand": staff_pay + staff_tip,
            }

        meal_sections = estimate.meal_sections()
        meal_total_amount = (
            sum((section["total"] for section in meal_sections), Decimal("0.00"))
            if meal_sections
            else Decimal("0.00")
        )
        sheet_surface_class = "sheet-surface-transparent" if caterer.document_surface_style == "TRANSPARENT" else ""
        sheet_background_class = f"sheet-bg--{caterer.document_background.lower()}"
        body_theme_class = "theme-bg-clean"
        service_style = "A la carte delivery" if estimate.is_ala_carte else "Full service catering"

        logo_url = None
        if caterer.brand_logo:
            logo_url = request.build_absolute_uri(caterer.brand_logo.url)

        context = {
            "estimate": estimate,
            "meal_sections": meal_sections,
            "extra_lines": extra_lines,
            "title": f"{'Invoice' if estimate.is_invoice else 'Estimate'} for {estimate.customer_name}",
            "auto_print": request.GET.get("print") == "1",
            "staff_context": staff_context,
            "brand_logo": logo_url,
            "brand_font": caterer.get_brand_font_stack(),
            "primary_color": caterer.brand_primary_color or "#0f172a",
            "accent_color": caterer.brand_accent_color or "#b08c6d",
            "sheet_surface_class": sheet_surface_class,
            "sheet_background_class": sheet_background_class,
            "body_theme_class": body_theme_class,
            "meal_total_amount": meal_total_amount,
            "service_style": service_style,
            "contact_lines": [
                line for line in [
                    caterer.company_phone,
                    caterer.company_email,
                    caterer.company_address,
                ] if line
            ],
            "bank_details": caterer.bank_details,
            "flat_mode": False,
        }
        return render(request, "admin/estimate_print.html", context)

    def print_estimate_flat(self, request, estimate_id):
        estimate = Estimate.objects.select_related("caterer", "caterer__owner").get(pk=estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        estimate.recalc_totals()
        extra_lines = (
            estimate.extra_lines.select_related("extra_item")
            .order_by("extra_item__category", "extra_item__name")
        )
        caterer = estimate.caterer
        staff_context = None
        if not estimate.is_ala_carte:
            waiters = estimate.total_waiter_count()
            staff_hours = estimate.staff_hours or Decimal("0.00")
            rate = estimate._get_staff_hourly_rate()
            tip = estimate._get_staff_tip_per_waiter()
            staff_pay = (rate * staff_hours * waiters).quantize(Decimal("0.01"))
            staff_tip = (tip * waiters).quantize(Decimal("0.01"))
            staff_context = {
                "waiters": waiters,
                "hours": staff_hours,
                "hourly_rate": rate,
                "labor_total": staff_pay,
                "tip_per_waiter": tip,
                "tip_total": staff_tip,
                "grand": staff_pay + staff_tip,
            }

        meal_sections = estimate.meal_sections()
        meal_total_amount = (
            sum((section["total"] + section.get("kids_total", Decimal("0.00")) for section in meal_sections), Decimal("0.00"))
            if meal_sections
            else Decimal("0.00")
        )
        sheet_surface_class = "sheet-surface-transparent" if caterer.document_surface_style == "TRANSPARENT" else ""
        sheet_background_class = f"sheet-bg--{caterer.document_background.lower()}"
        body_theme_class = "theme-bg-clean"
        service_style = "A la carte delivery" if estimate.is_ala_carte else "Full service catering"
        logo_url = None
        if caterer.brand_logo:
            logo_url = request.build_absolute_uri(caterer.brand_logo.url)

        total_guests = (estimate.guest_count or 0) + (estimate.guest_count_kids or 0)
        per_person = Decimal("0.00")
        if total_guests:
            per_person = (estimate.grand_total / Decimal(total_guests)).quantize(Decimal("0.01"))
        flat_deposit_pct = Decimal("30.00")
        flat_deposit_amount = (estimate.grand_total * Decimal("0.30")).quantize(Decimal("0.01"))
        flat_balance = (estimate.grand_total - flat_deposit_amount).quantize(Decimal("0.01"))

        context = {
            "estimate": estimate,
            "meal_sections": meal_sections,
            "extra_lines": extra_lines,
            "title": f"PP Flat Estimate for {estimate.customer_name}",
            "auto_print": request.GET.get("print") == "1",
            "staff_context": staff_context,
            "brand_logo": logo_url,
            "brand_font": caterer.get_brand_font_stack(),
            "primary_color": caterer.brand_primary_color or "#0f172a",
            "accent_color": caterer.brand_accent_color or "#b08c6d",
            "sheet_surface_class": sheet_surface_class,
            "sheet_background_class": sheet_background_class,
            "body_theme_class": body_theme_class,
            "meal_total_amount": meal_total_amount,
            "service_style": service_style,
            "contact_lines": [
                line for line in [
                    caterer.company_phone,
                    caterer.company_email,
                    caterer.company_address,
                ] if line
            ],
            "bank_details": caterer.bank_details,
            "flat_mode": True,
            "per_person_flat": per_person,
            "total_guests": total_guests,
            "flat_deposit_pct": flat_deposit_pct,
            "flat_deposit_amount": flat_deposit_amount,
            "flat_balance": flat_balance,
            "staff_context": None,  # hide staff section in flat mode
        }
        return render(request, "admin/estimate_print.html", context)

    def _workflow_payload(self, request, estimate):
        default_meal = estimate.default_meal_name()
        choices = (
            estimate.food_choices.select_related("menu_item", "menu_item__category")
            .order_by("menu_item__category__sort_order", "menu_item__category__name", "menu_item__name")
        )
        grouped = defaultdict(list)
        for choice in choices:
            meal_name = choice.meal_name or default_meal
            category = "Chef's Selection"
            order = 999
            if choice.menu_item and choice.menu_item.category:
                category = choice.menu_item.category.name
                order = choice.menu_item.category.sort_order or order
            grouped[(order, category)].append(
                {
                    "item": choice.menu_item.name if choice.menu_item else "",
                    "meal": meal_name,
                    "notes": choice.notes,
                }
            )
        sections = []
        for (order, category), rows in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
            sections.append({"category": category, "items": rows})

        extras = estimate.extra_lines.select_related("extra_item").order_by("extra_item__category", "extra_item__name")

        logo_url = None
        if estimate.caterer.brand_logo:
            logo_url = request.build_absolute_uri(estimate.caterer.brand_logo.url)

        return {
            "estimate": estimate,
            "sections": sections,
            "extras": extras,
            "logo_url": logo_url,
            "primary_color": estimate.caterer.brand_primary_color or "#0f172a",
            "accent_color": estimate.caterer.brand_accent_color or "#b08c6d",
        }

    def workflow_view(self, request, estimate_id):
        estimate = Estimate.objects.select_related("caterer", "caterer__owner").get(pk=estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        payload = self._workflow_payload(request, estimate)
        return render(
            request,
            "admin/estimate_workflow.html",
            {"workflows": [payload], "auto_print": request.GET.get("print") == "1"},
        )

    def workflow_bulk_view(self, request):
        ids = request.GET.get("ids", "")
        id_list = [int(pk) for pk in ids.split(",") if pk.isdigit()]
        qs = Estimate.objects.select_related("caterer", "caterer__owner")
        if not request.user.is_superuser:
            qs = qs.filter(caterer__owner=request.user)
        estimates = list(qs.filter(pk__in=id_list).order_by("event_date"))
        if not estimates:
            self.message_user(
                request,
                "No estimates found for workflow printing.",
                level=messages.WARNING,
            )
            return redirect("admin:client_estimates_estimate_changelist")
        payloads = [self._workflow_payload(request, estimate) for estimate in estimates]
        return render(
            request,
            "admin/estimate_workflow.html",
            {"workflows": payloads, "auto_print": request.GET.get("print") == "1"},
        )

    def _create_inline_menu_items(self, request):
        if request.method != "POST":
            return
        caterer_id = request.POST.get("caterer")
        if not caterer_id:
            return
        try:
            caterer = CatererAccount.objects.get(pk=caterer_id)
        except CatererAccount.DoesNotExist:
            return

        created = 0
        for key, value in request.POST.items():
            if not key.startswith("new_item_name_"):
                continue
            raw_cat_id = key.replace("new_item_name_", "")
            name = (value or "").strip()
            if not name:
                continue
            desc = (request.POST.get(f"new_item_description_{raw_cat_id}", "") or "").strip()
            cost_raw = (request.POST.get(f"new_item_cost_{raw_cat_id}", "") or "0").strip()
            markup_raw = (request.POST.get(f"new_item_markup_{raw_cat_id}", "") or str(caterer.default_food_markup or "3.00")).strip()
            servings_raw = (request.POST.get(f"new_item_servings_{raw_cat_id}", "") or "1").strip()

            try:
                cost = Decimal(cost_raw)
            except InvalidOperation:
                cost = Decimal("0.00")
            try:
                markup = Decimal(markup_raw)
            except InvalidOperation:
                markup = Decimal("3.00")
            try:
                servings = Decimal(servings_raw)
            except InvalidOperation:
                servings = Decimal("1.00")

            category = None
            if raw_cat_id and raw_cat_id.lower() not in {"none", "null"}:
                category = MenuCategory.objects.filter(pk=raw_cat_id, caterer=caterer).first()

            MenuItem.objects.create(
                caterer=caterer,
                category=category,
                name=name,
                description=desc,
                cost_per_serving=cost,
                markup=markup,
                default_servings_per_person=servings,
                is_active=True,
            )
            created += 1

        if created:
            self.message_user(
                request,
                f"Added {created} new menu item(s) to the catalog for this caterer.",
                level=messages.SUCCESS,
            )

    # Override changeform to allow preview actions (apply meal plan) without saving.
    def _changeform_view(self, request, object_id, form_url, extra_context):
        from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
        from django.contrib.admin.utils import flatten_fieldsets, unquote
        from django.forms.formsets import all_valid
        from django.contrib.admin import helpers
        from django.utils.translation import gettext as _
        from django.db import router

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField(
                "The field %s cannot be referenced." % to_field
            )

        if request.method == "POST" and "_saveasnew" in request.POST:
            object_id = None

        add = object_id is None

        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id), to_field)

            if request.method == "POST":
                if not self.has_change_permission(request, obj):
                    raise PermissionDenied
            else:
                if not self.has_view_or_change_permission(request, obj):
                    raise PermissionDenied

            if obj is None:
                return self._get_obj_does_not_exist_redirect(
                    request, self.opts, object_id
                )

        fieldsets = self.get_fieldsets(request, obj)

        # Inline "add new menu item" handler before binding the form so new items appear immediately
        if request.method == "POST":
            self._create_inline_menu_items(request)

        ModelForm = self.get_form(
            request, obj, change=not add, fields=flatten_fieldsets(fieldsets)
        )
        if request.method == "POST":
            form = ModelForm(request.POST, request.FILES, instance=obj)
            formsets, inline_instances = self._create_formsets(
                request,
                form.instance,
                change=not add,
            )
            form_validated = form.is_valid()
            if "_apply_meal_plan" in request.POST:
                form_validated = False
            if form_validated:
                new_object = self.save_form(request, form, change=not add)
            else:
                new_object = form.instance
            if all_valid(formsets) and form_validated:
                self.save_model(request, new_object, form, not add)
                self.save_related(request, form, formsets, not add)
                change_message = self.construct_change_message(
                    request, form, formsets, add
                )
                if add:
                    self.log_addition(request, new_object, change_message)
                    return self.response_add(request, new_object)
                else:
                    self.log_change(request, new_object, change_message)
                    return self.response_change(request, new_object)
            else:
                form_validated = False
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(
                    request, form.instance, change=False
                )
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(
                    request, obj, change=True
                )

        if not add and not self.has_change_permission(request, obj):
            readonly_fields = flatten_fieldsets(fieldsets)
        else:
            readonly_fields = self.get_readonly_fields(request, obj)
        admin_form = helpers.AdminForm(
            form,
            list(fieldsets),
            self.get_prepopulated_fields(request, obj)
            if add or self.has_change_permission(request, obj)
            else {},
            readonly_fields,
            model_admin=self,
        )
        media = self.media + admin_form.media

        inline_formsets = self.get_inline_formsets(
            request, formsets, inline_instances, obj
        )
        for inline_formset in inline_formsets:
            media += inline_formset.media

        if add:
            title = _("Add %s")
        elif self.has_change_permission(request, obj):
            title = _("Change %s")
        else:
            title = _("View %s")
        context = {
            **self.admin_site.each_context(request),
            "title": title % self.opts.verbose_name,
            "subtitle": str(obj) if obj else None,
            "adminform": admin_form,
            "object_id": object_id,
            "original": obj,
            "is_popup": IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
            "to_field": to_field,
            "media": media,
            "inline_admin_formsets": inline_formsets,
            "errors": helpers.AdminErrorList(form, formsets),
            "preserved_filters": self.get_preserved_filters(request),
        }

        if (
            request.method == "POST"
            and not form_validated
            and "_saveasnew" in request.POST
        ):
            context["show_save"] = False
            context["show_save_and_continue"] = False
            add = False

        context.update(extra_context or {})

        return self.render_change_form(
            request, context, add=add, change=not add, obj=obj, form_url=form_url
        )

    def response_change(self, request, obj):
        if "_convert_to_invoice" in request.POST:
            if not obj.is_invoice:
                obj.is_invoice = True
                if not obj.payment_instructions:
                    obj.payment_instructions = self._default_payment_instructions(obj.caterer)
                if not obj.payment_terms:
                    obj.payment_terms = obj.caterer.default_payment_terms
                obj.save()
                self.message_user(
                    request,
                    "Estimate converted into an invoice. Update the payment instructions before sending.",
                    level=messages.SUCCESS,
                )
            return redirect(
                reverse("admin:client_estimates_estimate_change", args=[obj.pk])
            )
        return super().response_change(request, obj)

    @staticmethod
    def _default_payment_instructions(caterer):
        details = [
            "Please remit the 30% deposit within 48 hours to confirm the booking.",
        ]
        if caterer.bank_details:
            details.append(caterer.bank_details)
        else:
            line = "Bank Transfer"
            if caterer.name:
                line += f": {caterer.name}"
            details.append(line)
        details.append("Reference the event date on your payment so we can match it quickly.")
        return "\n".join(details)

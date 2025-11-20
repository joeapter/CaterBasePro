from decimal import Decimal
import csv

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

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
                decoded = file.read().decode("utf-8-sig").splitlines()  # handle BOM
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

                    cost = Decimal(row["cost_per_serving"])
                    markup = Decimal(row["markup"]) if row.get("markup") else caterer.default_food_markup
                    servings = Decimal(row["default_servings_per_person"] or "1.0")
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

    def get_queryset(self, request):
        return limit_to_user_caterer(super().get_queryset(request), request)

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
        ]
        return custom + urls

    def print_estimate_button(self, obj):
        url = reverse("admin:client_estimates_estimate_print", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">Print PDF</a>', url)

    print_estimate_button.short_description = "Download"

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
        }
        return render(request, "admin/estimate_print.html", context)

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

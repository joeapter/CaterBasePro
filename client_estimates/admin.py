from decimal import Decimal, InvalidOperation
import csv
import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.utils import flatten_fieldsets, unquote
from django.core.exceptions import PermissionDenied
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.db.models import Count, F
from django.forms.formsets import all_valid
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from .models import (
    CatererAccount,
    MenuCategory,
    MenuItem,
    ExtraItem,
    Estimate,
    KiddushEstimate,
    EstimateFoodChoice,
    EstimateExtraItem,
    MenuTemplate,
    ClientInquiry,
    ClientProfile,
    CatererTask,
    TableclothOption,
    PlasticwareOption,
    TastingAppointment,
    TrialRequest,
    EstimateExpenseEntry,
    EstimateStaffTimeEntry,
    EstimatePlannerEntry,
    PlannerOptionCard,
    PlannerOptionIcon,
    PLANNER_ICON_KEY_CHOICES,
    PLANNER_SECTION_CHOICES,
    ShoppingList,
    ShoppingListItem,
    XpenzMobileToken,
)
from .kiddush_menu import ensure_kiddush_menu, ensure_kiddush_planning_fee_line

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


PLANNER_SECTION_LABELS = {code: label for code, label in PLANNER_SECTION_CHOICES}
PLANNER_GROUP_LABELS = {
    ("DECOR", "table_cloths"): "Table Cloths",
    ("DECOR", "chad_paami"): "Chad Paami",
    ("DECOR", "centerpieces"): "Centerpieces",
    ("DECOR", "features"): "Features",
    ("RENTALS", "furniture"): "Furniture",
    ("RENTALS", "addon_features"): "Addon Features",
    ("ORDERS", "bread_order"): "Bread Order",
    ("ORDERS", "dishes_order"): "Dishes Order",
    ("ORDERS", "tablecloth_order"): "Tablecloth Order",
    ("PRINTING", "sign"): "Sign",
    ("PRINTING", "invitations"): "Invitations",
    ("PRINTING", "placecards"): "Placecards",
    ("PRINTING", "menus"): "Menus",
    ("PRINTING", "signing_boards"): "Signing Boards",
    ("STAFFING", "staffing"): "Staffing",
    ("SPECIAL_REQUESTS", "special_requests"): "Special Requests",
}
PLANNER_ITEM_LABELS = {
    ("DECOR", "centerpieces", "floral"): "Floral",
    ("DECOR", "centerpieces", "balloon"): "Balloon",
    ("DECOR", "centerpieces", "lanterns"): "Lanterns",
    ("DECOR", "features", "balloon_feature"): "Balloon Feature",
    ("DECOR", "features", "floral_feature"): "Floral Feature",
    ("DECOR", "features", "other"): "Other",
    ("RENTALS", "furniture", "tables"): "Tables",
    ("RENTALS", "furniture", "chairs"): "Chairs",
    ("RENTALS", "furniture", "bars"): "Bars",
    ("RENTALS", "furniture", "couches"): "Couches",
    ("RENTALS", "addon_features", "chocolate_fountain_rental"): "Chocolate Fountain Rental",
    ("RENTALS", "addon_features", "projector_screen_speaker_rental"): "Projector + Screen + Speaker Rental",
}
PLANNER_FIELD_LABELS = {
    "color": "Color",
    "colors": "Colors",
    "fabric": "Fabric",
    "qty": "Qty",
    "style": "Style",
    "price": "Price",
    "price_per_table": "Price Per Table",
    "type": "Type",
    "shape": "Shape",
    "seat_qty": "Seat Qty",
    "table_qty": "Table Qty",
    "size": "Size",
    "qty_staff_needed": "Qty Of Staff Needed",
    "who_hired": "Who Has Been Hired",
    "notes": "Notes",
    "supplier": "Supplier",
}
PLANNER_REQUIRED_GROUPS = {
    "DECOR": [
        ("table_cloths", "Table Cloths"),
        ("chad_paami", "Chad Paami"),
        ("centerpieces", "Centerpieces"),
        ("features", "Features"),
    ],
    "RENTALS": [
        ("furniture", "Furniture"),
        ("addon_features", "Addon Features"),
    ],
    "ORDERS": [
        ("bread_order", "Bread Order"),
        ("dishes_order", "Dishes Order"),
        ("tablecloth_order", "Tablecloth Order"),
    ],
    "PRINTING": [
        ("sign", "Sign"),
        ("invitations", "Invitations"),
        ("placecards", "Placecards"),
        ("menus", "Menus"),
        ("signing_boards", "Signing Boards"),
    ],
    "STAFFING": [
        ("staffing", "Staffing"),
    ],
    "SPECIAL_REQUESTS": [
        ("special_requests", "Special Requests"),
    ],
}


def _humanize_planner_code(value):
    raw = (value or "").replace("_", " ").replace("-", " ").strip()
    if not raw:
        return ""
    return " ".join(part.capitalize() for part in raw.split())


def _planner_group_label(section, group_code):
    return PLANNER_GROUP_LABELS.get((section, group_code), _humanize_planner_code(group_code))


def _planner_item_label(section, group_code, item_code):
    if not item_code:
        return ""
    return PLANNER_ITEM_LABELS.get((section, group_code, item_code), _humanize_planner_code(item_code))


def _planner_field_label(field_code):
    return PLANNER_FIELD_LABELS.get(field_code, _humanize_planner_code(field_code))


PLANNER_ICON_KEY_SET = {code for code, _label in PLANNER_ICON_KEY_CHOICES}


def _infer_planner_icon_key(*parts):
    haystack = " ".join(str(part or "").lower() for part in parts)
    if any(token in haystack for token in ["table", "cloth", "linens"]):
        return "table"
    if any(token in haystack for token in ["chair", "couch", "sofa", "furniture"]):
        return "armchair"
    if any(token in haystack for token in ["staff", "waiter", "team", "hired"]):
        return "users"
    if any(token in haystack for token in ["print", "sign", "menu", "invitation", "placecard"]):
        return "printer"
    if any(token in haystack for token in ["note", "special request", "request"]):
        return "file"
    if any(token in haystack for token in ["order", "bread", "dishes"]):
        return "clipboard"
    if any(token in haystack for token in ["decor", "centerpiece", "floral", "balloon", "feature"]):
        return "sparkles"
    if any(
        token in haystack
        for token in [
            "rental",
            "machine",
            "projector",
            "screen",
            "speaker",
            "fountain",
            "chocolate",
            "cotton candy",
            "bar",
        ]
    ):
        return "package"
    return "circle"

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
    list_display = (
        "name",
        "sort_order_override",
        "caterer",
        "category",
        "menu_type",
        "cost_per_serving",
        "markup",
        "is_active",
    )
    list_editable = ("sort_order_override",)
    list_filter = ("caterer", "category", "menu_type", "is_active")
    search_fields = ("name",)
    change_list_template = "admin/menu_upload.html"
    ordering = ("category__sort_order", "category__name", "sort_order_override", "name")

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


@admin.register(EstimateExpenseEntry)
class EstimateExpenseEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "estimate",
        "created_by",
        "expense_text",
        "expense_amount",
        "is_manual_only",
        "voice_note_duration_seconds",
        "created_at",
    )
    list_filter = ("estimate__caterer", "created_at")
    search_fields = ("estimate__customer_name", "estimate__event_type", "note_text")
    readonly_fields = (
        "estimate",
        "created_by",
        "receipt_image",
        "voice_note",
        "voice_note_duration_seconds",
        "expense_text",
        "expense_amount",
        "is_manual_only",
        "note_text",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("estimate", "estimate__caterer")
        if request.user.is_superuser:
            return qs
        return qs.filter(estimate__caterer__owner=request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.estimate.caterer.owner == request.user

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return obj and obj.estimate.caterer.owner == request.user


@admin.register(XpenzMobileToken)
class XpenzMobileTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "last_used_at", "updated_at", "created_at")
    readonly_fields = ("user", "key", "created_at", "updated_at", "last_used_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("created_at", "last_used_at")

    def has_add_permission(self, request):
        return False


@admin.register(EstimateStaffTimeEntry)
class EstimateStaffTimeEntryAdmin(admin.ModelAdmin):
    class EstimateStaffTimeEntryAdminForm(forms.ModelForm):
        class Meta:
            model = EstimateStaffTimeEntry
            fields = "__all__"

        def clean(self):
            cleaned = super().clean()
            punched_in_at = cleaned.get("punched_in_at")
            punched_out_at = cleaned.get("punched_out_at")
            if punched_in_at and punched_out_at and punched_out_at < punched_in_at:
                self.add_error(
                    "punched_out_at",
                    "Punch out time must be after punch in time.",
                )
            return cleaned

    form = EstimateStaffTimeEntryAdminForm
    list_display = (
        "estimate",
        "worker_first_name",
        "role",
        "hourly_rate",
        "punched_in_at",
        "punched_out_at",
        "total_hours",
        "total_cost",
        "applied_to_expenses",
    )
    list_filter = ("role", "applied_to_expenses", "estimate__caterer")
    search_fields = ("worker_first_name", "estimate__customer_name", "estimate__event_type")
    readonly_fields = (
        "estimate",
        "applied_to_expenses",
        "expense_entry",
        "total_hours",
        "total_cost",
        "created_by",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("estimate", "estimate__caterer")
        if request.user.is_superuser:
            return qs
        return qs.filter(estimate__caterer__owner=request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return False
        return obj.estimate.caterer.owner == request.user

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return False
        return obj.estimate.caterer.owner == request.user

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.applied_to_expenses:
            readonly.extend(
                [
                    "role",
                    "worker_first_name",
                    "hourly_rate",
                    "punched_in_at",
                    "punched_out_at",
                ]
            )
        return tuple(readonly)

    def save_model(self, request, obj, form, change):
        if obj.punched_out_at:
            if obj.punched_out_at < obj.punched_in_at:
                obj.punched_out_at = obj.punched_in_at
            seconds = (obj.punched_out_at - obj.punched_in_at).total_seconds()
            hours = Decimal(str(seconds / 3600)) if seconds > 0 else Decimal("0.00")
            obj.total_hours = hours.quantize(Decimal("0.01"))
            obj.total_cost = (
                (obj.total_hours or Decimal("0.00")) * (obj.hourly_rate or Decimal("0.00"))
            ).quantize(Decimal("0.01"))
        else:
            obj.total_hours = Decimal("0.00")
            obj.total_cost = Decimal("0.00")
        super().save_model(request, obj, form, change)


@admin.register(EstimatePlannerEntry)
class EstimatePlannerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "estimate",
        "section",
        "group_code",
        "item_code",
        "is_checked",
        "sort_order",
        "updated_at",
    )
    list_filter = ("section", "caterer", "is_checked")
    search_fields = ("estimate__customer_name", "group_code", "item_code", "notes")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("estimate", "caterer")
        if request.user.is_superuser:
            return qs
        return qs.filter(caterer__owner=request.user)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        if obj.estimate_id and not obj.caterer_id:
            obj.caterer = obj.estimate.caterer
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return obj.caterer.owner == request.user


@admin.register(PlannerOptionIcon)
class PlannerOptionIconAdmin(admin.ModelAdmin):
    change_list_template = "admin/client_estimates/planneroptionicon/change_list.html"
    list_display = (
        "caterer",
        "section",
        "group_code",
        "item_code",
        "icon_key",
        "is_manual_override",
        "updated_by",
        "updated_at",
    )
    list_editable = ("icon_key", "is_manual_override")
    list_filter = ("section", "icon_key", "is_manual_override", "caterer")
    search_fields = ("caterer__name", "group_code", "item_code")
    ordering = ("caterer__name", "section", "group_code", "item_code")
    list_select_related = ("caterer", "updated_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("caterer", "updated_by")
        return limit_to_user_caterer(qs, request)

    def has_module_permission(self, request):
        return request.user.is_superuser or CatererAccount.objects.filter(owner=request.user).exists()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return self.has_module_permission(request)
        return obj.caterer.owner == request.user

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return self.has_module_permission(request)
        return obj.caterer.owner == request.user

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return False
        return obj.caterer.owner == request.user

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "refresh-icons/",
                self.admin_site.admin_view(self.refresh_icons),
                name="client_estimates_planneroptionicon_refresh_icons",
            ),
        ]
        return custom + urls

    def refresh_icons(self, request):
        if request.method != "POST":
            return redirect("admin:client_estimates_planneroptionicon_changelist")

        if request.user.is_superuser:
            caterer_ids = list(CatererAccount.objects.values_list("id", flat=True))
        else:
            caterer_ids = list(CatererAccount.objects.filter(owner=request.user).values_list("id", flat=True))

        if not caterer_ids:
            self.message_user(request, "No accessible caterers found.", level=messages.WARNING)
            return redirect("admin:client_estimates_planneroptionicon_changelist")

        option_map = {}
        for row in PlannerOptionCard.objects.filter(caterer_id__in=caterer_ids).values(
            "caterer_id",
            "section",
            "group_code",
            "item_code",
            "item_label",
        ):
            caterer_id = row.get("caterer_id")
            section = row.get("section") or ""
            group_code = row.get("group_code") or ""
            item_code = row.get("item_code") or ""
            if not caterer_id or not section or not group_code or not item_code:
                continue
            key = (caterer_id, section, group_code, item_code)
            option_map[key] = {
                "caterer_id": caterer_id,
                "section": section,
                "group_code": group_code,
                "item_code": item_code,
                "item_label": (row.get("item_label") or "").strip(),
            }

        usage_rows = (
            EstimatePlannerEntry.objects.filter(caterer_id__in=caterer_ids)
            .exclude(item_code="")
            .values("caterer_id", "section", "group_code", "item_code")
            .annotate(usage_count=Count("id"))
            .order_by("caterer_id", "section", "group_code", "item_code")
        )
        for row in usage_rows:
            caterer_id = row["caterer_id"]
            section = row["section"] or ""
            group_code = row["group_code"] or ""
            item_code = row["item_code"] or ""
            if not section or not group_code or not item_code:
                continue
            key = (caterer_id, section, group_code, item_code)
            if key not in option_map:
                option_map[key] = {
                    "caterer_id": caterer_id,
                    "section": section,
                    "group_code": group_code,
                    "item_code": item_code,
                    "item_label": _planner_item_label(section, group_code, item_code),
                }
        rows = list(option_map.values())

        existing = {
            (row.caterer_id, row.section, row.group_code, row.item_code): row
            for row in PlannerOptionIcon.objects.filter(caterer_id__in=caterer_ids)
        }

        created_count = 0
        updated_count = 0
        skipped_manual_count = 0
        for row in rows:
            caterer_id = row["caterer_id"]
            section = row["section"] or ""
            group_code = row["group_code"] or ""
            item_code = row["item_code"] or ""
            item_label = row.get("item_label") or _planner_item_label(section, group_code, item_code)
            if not section or not group_code or not item_code:
                continue
            key = (caterer_id, section, group_code, item_code)
            inferred_icon = _infer_planner_icon_key(section, group_code, item_code, item_label)
            if inferred_icon not in PLANNER_ICON_KEY_SET:
                inferred_icon = "circle"
            existing_row = existing.get(key)
            if existing_row and existing_row.is_manual_override:
                skipped_manual_count += 1
                continue
            if not existing_row:
                PlannerOptionIcon.objects.create(
                    caterer_id=caterer_id,
                    section=section,
                    group_code=group_code,
                    item_code=item_code,
                    icon_key=inferred_icon,
                    is_manual_override=False,
                    updated_by=request.user,
                )
                created_count += 1
                continue

            changed = []
            if existing_row.icon_key != inferred_icon:
                existing_row.icon_key = inferred_icon
                changed.append("icon_key")
            if existing_row.is_manual_override:
                existing_row.is_manual_override = False
                changed.append("is_manual_override")
            if existing_row.updated_by_id != request.user.id:
                existing_row.updated_by = request.user
                changed.append("updated_by")
            if changed:
                changed.append("updated_at")
                existing_row.save(update_fields=changed)
                updated_count += 1

        self.message_user(
            request,
            (
                "Global planner icon refresh finished. "
                f"Created: {created_count}, updated: {updated_count}, "
                f"manual overrides kept: {skipped_manual_count}."
            ),
            level=messages.SUCCESS,
        )
        return redirect("admin:client_estimates_planneroptionicon_changelist")


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "caterer",
        "estimate",
        "execution_started_by",
        "execution_started_at",
        "created_by",
        "updated_at",
        "created_at",
    )
    list_filter = ("caterer", "execution_started_at", "created_at", "updated_at")
    search_fields = ("title", "caterer__name", "estimate__customer_name", "estimate__event_type")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("caterer", "estimate", "created_by")
        if request.user.is_superuser:
            return qs
        return qs.filter(caterer__owner=request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and "caterer" in form.base_fields:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(owner=request.user)
        if not request.user.is_superuser and "estimate" in form.base_fields:
            form.base_fields["estimate"].queryset = Estimate.objects.filter(caterer__owner=request.user)
        return form


@admin.register(ShoppingListItem)
class ShoppingListItemAdmin(admin.ModelAdmin):
    @admin.display(description="Organization", ordering="shopping_list__caterer__name")
    def organization(self, obj):
        if obj.shopping_list_id and obj.shopping_list.caterer_id:
            return obj.shopping_list.caterer.name
        return "-"

    list_display = (
        "organization",
        "shopping_list",
        "item_name",
        "item_type",
        "item_unit",
        "quantity",
        "category",
        "collaboration_note",
        "is_completed",
        "completed_by",
        "completed_at",
        "created_by",
        "created_at",
    )
    list_filter = (
        "shopping_list__caterer",
        "category",
        "is_completed",
        "collaboration_note",
        "created_at",
    )
    search_fields = (
        "item_name",
        "item_type",
        "item_unit",
        "shopping_list__title",
        "shopping_list__caterer__name",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("shopping_list", "shopping_list__caterer")
        if request.user.is_superuser:
            return qs
        return qs.filter(shopping_list__caterer__owner=request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and "shopping_list" in form.base_fields:
            form.base_fields["shopping_list"].queryset = ShoppingList.objects.filter(
                caterer__owner=request.user
            )
        return form


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

                    def parse_int(value):
                        try:
                            raw = str(value).strip() if value is not None else ""
                            if not raw:
                                return None
                            return int(Decimal(raw))
                        except (InvalidOperation, ValueError):
                            return None

                    cost = parse_decimal(row.get("cost_per_serving"), "0.0")
                    markup = parse_decimal(row.get("markup"), str(caterer.default_food_markup))
                    if markup == Decimal("0.0"):
                        markup = caterer.default_food_markup
                    servings = parse_decimal(row.get("default_servings_per_person"), "1.0")
                    is_active = str(row.get("is_active", "true")).lower() == "true"
                    sort_override = parse_int(row.get("sort_order_override"))

                    if item_type == "food":
                        MenuItem.objects.create(
                            caterer=caterer,
                            category=category,
                            name=name,
                            description=row.get("description", ""),
                            sort_order_override=sort_override,
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
            "sort_order_override",
            "cost_per_serving",
            "markup",
            "default_servings_per_person",
            "is_active",
        ]
        sample_rows = [
            ["Food", "Starters", "Smoked Salmon Bites", "Mini bagels with lox", "1", "12.50", "3.0", "1.0", "True"],
            ["Food", "Mains", "Steak Strip", "Grilled steak strips", "", "28.00", "", "1.0", "True"],
            ["Extra", "Rental", "Projector", "", "", "400", "3.0", "1.0", "True"],
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
    list_display = ("name", "caterer", "menu_type", "created_at")
    list_filter = ("menu_type", "caterer")
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
    menu_type = "STANDARD"
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
    meal_guest_overrides_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    meal_service_json = forms.CharField(
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
        menu_type = getattr(self, "menu_type", "STANDARD")

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
                caterer=caterer,
                menu_type=menu_type,
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
            self.fields["meal_guest_overrides_json"].initial = json.dumps(
                self.instance.meal_guest_overrides or {}
            )
            self.fields["meal_service_json"].initial = json.dumps(
                self.instance.meal_service_details or {}
            )
            if "tablecloth_details" in self.fields:
                self.fields["tablecloth_details"].initial = json.dumps(
                    self.instance.tablecloth_details or {}
                )
        if "tablecloth_details" in self.fields:
            self.fields["tablecloth_details"].required = False
            self.fields["tablecloth_details"].widget = forms.HiddenInput()

        # Build dynamic item checklist
        self.menu_items = []
        if caterer:
            menu_qs = (
                MenuItem.objects.filter(
                    caterer=caterer,
                    is_active=True,
                    menu_type=menu_type,
                )
                .select_related("category")
                .order_by(
                    F("category__sort_order").asc(nulls_last=True),
                    F("category__name").asc(nulls_last=True),
                    F("sort_order_override").asc(nulls_last=True),
                    "name",
                )
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

        # Suggestions for remembered options
        self.tablecloth_options = []
        self.plasticware_options = []
        if caterer:
            self.tablecloth_options = list(
                TableclothOption.objects.filter(caterer=caterer)
                .order_by("name")
                .values_list("name", flat=True)
            )
            self.plasticware_options = list(
                PlasticwareOption.objects.filter(caterer=caterer)
                .order_by("name")
                .values_list("name", flat=True)
            )
        if "plasticware_color" in self.fields:
            self.fields["plasticware_color"].required = False
            self.fields["plasticware_color"].widget.attrs["list"] = "plasticware-options"
            self.fields["plasticware_color"].widget.attrs.setdefault(
                "placeholder",
                "e.g. Gold / Silver / Clear",
            )


class KiddushEstimateAdminForm(EstimateAdminForm):
    menu_type = "KIDDUSH"

    def __init__(self, *args, **kwargs):
        request = kwargs.get("request")
        instance = kwargs.get("instance")
        caterer = None
        if instance and instance.pk and instance.caterer_id:
            caterer = instance.caterer
        elif request:
            caterer = CatererAccount.objects.filter(owner=request.user).first()
        if caterer:
            ensure_kiddush_menu(caterer)
        super().__init__(*args, **kwargs)


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    form = EstimateAdminForm
    change_form_template = "admin/estimate_change_form.html"
    estimate_type = "STANDARD"
    menu_type = "STANDARD"

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
                    "kids_discount_percentage",
                    "exchange_rate",
                    "include_premium_plastic",
                    "include_premium_tablecloths",
                    "plasticware_color",
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
                    "staff_count_override",
                    "staff_hourly_rate",
                    "staff_tip_per_waiter",
                    "client_tipped_at_event",
                    "notes_internal",
                    "notes_for_customer",
                    "deposit_percentage",
                    "deposit_received",
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
        qs = limit_to_user_caterer(super().get_queryset(request), request)
        if self.estimate_type:
            qs = qs.filter(estimate_type=self.estimate_type)
        return qs

    def _admin_url_name(self, suffix):
        return f"{self.opts.app_label}_{self.opts.model_name}_{suffix}"

    def _admin_reverse(self, suffix, args=None):
        return reverse(f"admin:{self._admin_url_name(suffix)}", args=args)

    def _get_estimate(self, estimate_id):
        qs = Estimate.objects.select_related("caterer", "caterer__owner")
        if self.estimate_type:
            qs = qs.filter(estimate_type=self.estimate_type)
        return qs.get(pk=estimate_id)

    def workflow_bulk_action(self, request, queryset):
        ids = list(queryset.values_list("pk", flat=True))
        if not ids:
            self.message_user(request, "Select at least one estimate to print workflows.", level=messages.WARNING)
            return
        url = self._admin_reverse("workflow_bulk")
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

    def _parse_tablecloths(self, raw_value, meal_names):
        if isinstance(raw_value, str):
            try:
                raw_value = json.loads(raw_value) if raw_value else {}
            except json.JSONDecodeError:
                raw_value = {}
        if not isinstance(raw_value, dict):
            return {}

        ordered_meals = list(meal_names)
        for key in raw_value.keys():
            if key not in ordered_meals:
                ordered_meals.append(key)

        parsed = {}
        for meal in ordered_meals:
            entry = raw_value.get(meal) or {}
            name = (entry.get("name") or entry.get("choice") or "").strip()
            qty = Estimate._clean_decimal(entry.get("quantity"), Decimal("0.00")) or Decimal("0.00")
            extra = Estimate._clean_decimal(entry.get("extra_charge"), None)
            has_price = extra not in (None, Decimal("0.00"))

            if not name and (qty in (None, Decimal("0.00"))) and not has_price:
                continue

            parsed[meal] = {
                "name": name,
                "quantity": str(qty.quantize(Decimal("0.01"))),
                "extra_charge": None if not has_price else str(extra.quantize(Decimal("0.01"))),
            }
        return parsed

    def _remember_material_choices(self, caterer, tablecloth_data, plasticware_value):
        if not caterer:
            return
        for entry in (tablecloth_data or {}).values():
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            cloth, created = TableclothOption.objects.get_or_create(
                caterer=caterer,
                name=name,
            )
            if not created:
                cloth.save(update_fields=["last_used_at"])

        plastic = (plasticware_value or "").strip()
        if plastic:
            option, created = PlasticwareOption.objects.get_or_create(
                caterer=caterer,
                name=plastic,
            )
            if not created:
                option.save(update_fields=["last_used_at"])

    def save_model(self, request, obj, form, change):
        """
        Save the Estimate, then build EstimateFoodChoice rows based on
        the checkbox selection and template usage. Also optionally save a new template.
        """
        is_new = obj.pk is None
        if self.estimate_type:
            obj.estimate_type = self.estimate_type
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
        guest_overrides_raw = form.cleaned_data.get("meal_guest_overrides_json")
        try:
            obj.meal_guest_overrides = json.loads(guest_overrides_raw) if guest_overrides_raw else {}
        except json.JSONDecodeError:
            obj.meal_guest_overrides = {}
        service_raw = form.cleaned_data.get("meal_service_json")
        try:
            obj.meal_service_details = json.loads(service_raw) if service_raw else {}
        except json.JSONDecodeError:
            obj.meal_service_details = {}
        obj.tablecloth_details = self._parse_tablecloths(
            form.cleaned_data.get("tablecloth_details"),
            meal_names,
        )

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
                menu_type=self.menu_type,
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
        self._remember_material_choices(
            obj.caterer,
            obj.tablecloth_details,
            form.cleaned_data.get("plasticware_color"),
        )
        # After rebuilding related rows, recalc totals now that selections exist
        obj.save()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:estimate_id>/print/",
                self.admin_site.admin_view(self.print_estimate),
                name=self._admin_url_name("print"),
            ),
            path(
                "<int:estimate_id>/print-flat/",
                self.admin_site.admin_view(self.print_estimate_flat),
                name=self._admin_url_name("print_flat"),
            ),
            path(
                "<int:estimate_id>/planner-print/",
                self.admin_site.admin_view(self.print_planner),
                name=self._admin_url_name("planner_print"),
            ),
            path(
                "<int:estimate_id>/planner-icons/",
                self.admin_site.admin_view(self.planner_icons_manager),
                name=self._admin_url_name("planner_icons"),
            ),
            path(
                "<int:estimate_id>/planner-icons/refresh/",
                self.admin_site.admin_view(self.refresh_planner_icons),
                name=self._admin_url_name("planner_icons_refresh"),
            ),
            path(
                "<int:estimate_id>/workflow/",
                self.admin_site.admin_view(self.workflow_view),
                name=self._admin_url_name("workflow"),
            ),
            path(
                "workflow/bulk/",
                self.admin_site.admin_view(self.workflow_bulk_view),
                name=self._admin_url_name("workflow_bulk"),
            ),
            path(
                "<int:estimate_id>/expenses/<int:entry_id>/delete/",
                self.admin_site.admin_view(self.delete_expense_entry),
                name=self._admin_url_name("expense_delete"),
            ),
        ]
        return custom + urls

    def print_estimate_button(self, obj):
        url = self._admin_reverse("print", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">Print PDF</a>', url)

    print_estimate_button.short_description = "Download"

    def workflow_button(self, obj):
        url = self._admin_reverse("workflow", args=[obj.pk])
        return format_html('<a class="button" target="_blank" href="{}">Workflow</a>', f"{url}?print=1")

    workflow_button.short_description = "Kitchen"

    def flat_print_button(self, obj):
        url = self._admin_reverse("print_flat", args=[obj.pk])
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

    def delete_expense_entry(self, request, estimate_id, entry_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")

        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "Method not allowed."}, status=405)

        entry = get_object_or_404(
            EstimateExpenseEntry,
            pk=entry_id,
            estimate=estimate,
        )
        entry.delete()
        self.message_user(request, "Expense entry removed.", level=messages.SUCCESS)
        return JsonResponse({"ok": True})

    def _planner_option_catalog_for_caterer(self, caterer_id):
        payload_map = {}

        option_rows = (
            PlannerOptionCard.objects.filter(caterer_id=caterer_id)
            .values("section", "group_code", "item_code", "item_label", "sort_order")
            .order_by("section", "group_code", "sort_order", "item_label", "item_code")
        )
        for row in option_rows:
            section = row.get("section") or ""
            group_code = row.get("group_code") or ""
            item_code = row.get("item_code") or ""
            if not section or not group_code or not item_code:
                continue
            key = (section, group_code, item_code)
            payload_map[key] = {
                "section": section,
                "section_label": PLANNER_SECTION_LABELS.get(section, section),
                "group_code": group_code,
                "group_label": _planner_group_label(section, group_code),
                "item_code": item_code,
                "item_label": (row.get("item_label") or "").strip()
                or _planner_item_label(section, group_code, item_code),
                "usage_count": 0,
                "sort_order": int(row.get("sort_order") or 0),
            }

        usage_rows = (
            EstimatePlannerEntry.objects.filter(caterer_id=caterer_id)
            .exclude(item_code="")
            .values("section", "group_code", "item_code")
            .annotate(usage_count=Count("id"))
            .order_by("section", "group_code", "item_code")
        )
        for row in usage_rows:
            section = row.get("section") or ""
            group_code = row.get("group_code") or ""
            item_code = row.get("item_code") or ""
            if not section or not group_code or not item_code:
                continue
            key = (section, group_code, item_code)
            if key not in payload_map:
                payload_map[key] = {
                    "section": section,
                    "section_label": PLANNER_SECTION_LABELS.get(section, section),
                    "group_code": group_code,
                    "group_label": _planner_group_label(section, group_code),
                    "item_code": item_code,
                    "item_label": _planner_item_label(section, group_code, item_code),
                    "usage_count": 0,
                    "sort_order": 9999,
                }
            payload_map[key]["usage_count"] = int(payload_map[key]["usage_count"]) + int(
                row.get("usage_count") or 0
            )

        payload = list(payload_map.values())
        payload.sort(
            key=lambda row: (
                row.get("section") or "",
                row.get("group_code") or "",
                int(row.get("sort_order") or 0),
                (row.get("item_label") or "").lower(),
                row.get("item_code") or "",
            )
        )
        for row in payload:
            row.pop("sort_order", None)
        return payload

    def _refresh_planner_icons_for_caterer(self, caterer, user):
        option_rows = self._planner_option_catalog_for_caterer(caterer.id)
        existing = {
            (row.section, row.group_code, row.item_code): row
            for row in PlannerOptionIcon.objects.filter(caterer=caterer)
        }
        created_count = 0
        updated_count = 0
        skipped_manual_count = 0
        for row in option_rows:
            section = row["section"]
            group_code = row["group_code"]
            item_code = row["item_code"]
            key = (section, group_code, item_code)
            inferred_icon = _infer_planner_icon_key(
                section,
                row["group_label"],
                row["item_label"],
                group_code,
                item_code,
            )
            if inferred_icon not in PLANNER_ICON_KEY_SET:
                inferred_icon = "circle"
            existing_row = existing.get(key)
            if existing_row and existing_row.is_manual_override:
                skipped_manual_count += 1
                continue
            if not existing_row:
                PlannerOptionIcon.objects.create(
                    caterer=caterer,
                    section=section,
                    group_code=group_code,
                    item_code=item_code,
                    icon_key=inferred_icon,
                    is_manual_override=False,
                    updated_by=user,
                )
                created_count += 1
                continue
            changed = []
            if existing_row.icon_key != inferred_icon:
                existing_row.icon_key = inferred_icon
                changed.append("icon_key")
            if existing_row.is_manual_override:
                existing_row.is_manual_override = False
                changed.append("is_manual_override")
            if existing_row.updated_by_id != user.id:
                existing_row.updated_by = user
                changed.append("updated_by")
            if changed:
                changed.append("updated_at")
                existing_row.save(update_fields=changed)
                updated_count += 1
        return {
            "created": created_count,
            "updated": updated_count,
            "skipped_manual": skipped_manual_count,
            "total": len(option_rows),
        }

    def refresh_planner_icons(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        if request.method != "POST":
            return redirect(self._admin_reverse("change", args=[estimate.pk]))
        summary = self._refresh_planner_icons_for_caterer(estimate.caterer, request.user)
        self.message_user(
            request,
            (
                "Planner icons refreshed. "
                f"Created: {summary['created']}, updated: {summary['updated']}, "
                f"manual overrides kept: {summary['skipped_manual']}."
            ),
            level=messages.SUCCESS,
        )
        return redirect(self._admin_reverse("planner_icons", args=[estimate.pk]))

    def planner_icons_manager(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")

        if request.method == "POST" and "_refresh_icons" in request.POST:
            summary = self._refresh_planner_icons_for_caterer(estimate.caterer, request.user)
            self.message_user(
                request,
                (
                    "Planner icons refreshed. "
                    f"Created: {summary['created']}, updated: {summary['updated']}, "
                    f"manual overrides kept: {summary['skipped_manual']}."
                ),
                level=messages.SUCCESS,
            )
            return redirect(self._admin_reverse("planner_icons", args=[estimate.pk]))

        option_rows = self._planner_option_catalog_for_caterer(estimate.caterer_id)
        existing = {
            (row.section, row.group_code, row.item_code): row
            for row in PlannerOptionIcon.objects.filter(caterer=estimate.caterer)
        }

        if request.method == "POST" and "_save_overrides" in request.POST:
            updated_count = 0
            cleared_count = 0
            for index, row in enumerate(option_rows):
                section = row["section"]
                group_code = row["group_code"]
                item_code = row["item_code"]
                key = (section, group_code, item_code)
                inferred_icon = _infer_planner_icon_key(
                    section,
                    row["group_label"],
                    row["item_label"],
                    group_code,
                    item_code,
                )
                if inferred_icon not in PLANNER_ICON_KEY_SET:
                    inferred_icon = "circle"
                requested_icon = (request.POST.get(f"icon__{index}") or inferred_icon).strip()
                if requested_icon not in PLANNER_ICON_KEY_SET:
                    requested_icon = inferred_icon
                manual_override = request.POST.get(f"manual__{index}") == "1"
                existing_row = existing.get(key)

                if not manual_override and requested_icon == inferred_icon:
                    if existing_row:
                        existing_row.delete()
                        cleared_count += 1
                    continue

                if not existing_row:
                    PlannerOptionIcon.objects.create(
                        caterer=estimate.caterer,
                        section=section,
                        group_code=group_code,
                        item_code=item_code,
                        icon_key=requested_icon,
                        is_manual_override=manual_override,
                        updated_by=request.user,
                    )
                    updated_count += 1
                    continue

                changed = []
                if existing_row.icon_key != requested_icon:
                    existing_row.icon_key = requested_icon
                    changed.append("icon_key")
                if existing_row.is_manual_override != manual_override:
                    existing_row.is_manual_override = manual_override
                    changed.append("is_manual_override")
                if existing_row.updated_by_id != request.user.id:
                    existing_row.updated_by = request.user
                    changed.append("updated_by")
                if changed:
                    changed.append("updated_at")
                    existing_row.save(update_fields=changed)
                    updated_count += 1

            self.message_user(
                request,
                f"Planner icon overrides saved. Updated: {updated_count}, cleared: {cleared_count}.",
                level=messages.SUCCESS,
            )
            return redirect(self._admin_reverse("planner_icons", args=[estimate.pk]))

        display_rows = []
        for row in option_rows:
            key = (row["section"], row["group_code"], row["item_code"])
            inferred_icon = _infer_planner_icon_key(
                row["section"],
                row["group_label"],
                row["item_label"],
                row["group_code"],
                row["item_code"],
            )
            if inferred_icon not in PLANNER_ICON_KEY_SET:
                inferred_icon = "circle"
            override = existing.get(key)
            current_icon = override.icon_key if override else inferred_icon
            display_rows.append(
                {
                    **row,
                    "inferred_icon": inferred_icon,
                    "current_icon": current_icon,
                    "is_manual_override": bool(override and override.is_manual_override),
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Planner Icon Overrides - {estimate.customer_name}",
            "estimate": estimate,
            "option_rows": display_rows,
            "icon_choices": PLANNER_ICON_KEY_CHOICES,
            "change_url": self._admin_reverse("change", args=[estimate.pk]),
            "refresh_url": self._admin_reverse("planner_icons_refresh", args=[estimate.pk]),
        }
        return render(request, "admin/estimate_planner_icons.html", context)

    def _planner_sections_for_estimate(self, estimate):
        entries = list(
            estimate.planner_entries.order_by("section", "sort_order", "created_at")
        )
        grouped = {}
        section_order = {code: idx for idx, (code, _label) in enumerate(PLANNER_SECTION_CHOICES)}

        for entry in entries:
            data_rows = []
            for field_code, value in (entry.data or {}).items():
                data_rows.append(
                    {
                        "field_code": field_code,
                        "field_label": _planner_field_label(field_code),
                        "value": value,
                    }
                )
            data_rows.sort(key=lambda row: row["field_label"].lower())
            grouped.setdefault(entry.section, []).append(
                {
                    "id": entry.id,
                    "section": entry.section,
                    "section_label": PLANNER_SECTION_LABELS.get(entry.section, entry.section),
                    "group_code": entry.group_code,
                    "group_label": _planner_group_label(entry.section, entry.group_code),
                    "item_code": entry.item_code,
                    "item_label": _planner_item_label(entry.section, entry.group_code, entry.item_code),
                    "data_rows": data_rows,
                    "notes": entry.notes,
                    "is_checked": bool(entry.is_checked),
                    "sort_order": entry.sort_order,
                }
            )

        sections = []
        for section_code, section_label in PLANNER_SECTION_CHOICES:
            rows = grouped.get(section_code, [])
            if not rows:
                continue
            sections.append(
                {
                    "code": section_code,
                    "label": section_label,
                    "items": rows,
                }
            )
        sections.sort(key=lambda row: section_order.get(row["code"], 999))
        return sections

    def _planner_missing_groups_for_estimate(self, estimate):
        existing_pairs = set(
            estimate.planner_entries.values_list("section", "group_code")
        )
        missing_sections = []
        for section_code, section_label in PLANNER_SECTION_CHOICES:
            required_groups = PLANNER_REQUIRED_GROUPS.get(section_code, [])
            missing = []
            for group_code, fallback_label in required_groups:
                if (section_code, group_code) in existing_pairs:
                    continue
                missing.append(
                    {
                        "group_code": group_code,
                        "group_label": PLANNER_GROUP_LABELS.get(
                            (section_code, group_code), fallback_label
                        ),
                    }
                )
            if missing:
                missing_sections.append(
                    {
                        "code": section_code,
                        "label": section_label,
                        "items": missing,
                    }
                )
        return missing_sections

    def print_planner(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")

        planner_sections = self._planner_sections_for_estimate(estimate)
        context = {
            "estimate": estimate,
            "planner_sections": planner_sections,
            "title": f"Planning Checklist for {estimate.customer_name}",
            "auto_print": request.GET.get("print") == "1",
        }
        return render(request, "admin/estimate_planner_print.html", context)

    def print_estimate(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        estimate.recalc_totals()

        extra_lines = (
            estimate.extra_lines.select_related("extra_item")
            .order_by("extra_item__category", "extra_item__name")
        )
        fx_rate = (estimate.exchange_rate or Decimal("1.00"))
        extras_rows = []
        for line in extra_lines:
            base_price = line.override_price if line.override_price is not None else line.extra_item.price
            display_price = None
            if base_price is not None:
                display_price = (base_price * fx_rate).quantize(Decimal("0.01"))
            extras_rows.append(
                {
                    "name": line.extra_item.name,
                    "quantity": line.quantity,
                    "notes": line.notes,
                    "charge_type": line.extra_item.get_charge_type_display(),
                    "price": display_price,
                    "is_included": display_price in (None, Decimal("0.00")),
                }
            )

        per_meal_service_rows = estimate.per_meal_service_summary()
        show_delivery_fee = any(row.get("wants_real_dishes") for row in per_meal_service_rows)
        delivery_fee = (
            estimate.real_dishes_flat_fee
            or (estimate.caterer.real_dishes_flat_fee if estimate.caterer_id else Decimal("0.00"))
            or Decimal("0.00")
        )
        if estimate.exchange_rate and estimate.exchange_rate != Decimal("1.00"):
            delivery_fee = (delivery_fee * estimate.exchange_rate).quantize(Decimal("0.01"))
        dishes_delivery_fee = Decimal("0.00")
        dishes_subtotal = estimate.dishes_total
        if estimate.dishes_total:
            dishes_delivery_fee = min(delivery_fee, estimate.dishes_total)
            dishes_subtotal = (estimate.dishes_total - dishes_delivery_fee).quantize(Decimal("0.01"))
        caterer = estimate.caterer
        staff_context = None
        if not estimate.is_ala_carte:
            waiters = estimate.total_waiter_count()
            rate = estimate._get_staff_hourly_rate()
            if per_meal_service_rows:
                staff_hours = sum((row["staff_hours"] for row in per_meal_service_rows), Decimal("0.00")).quantize(Decimal("0.01"))
                staff_pay = sum((row["staff_pay_total"] for row in per_meal_service_rows), Decimal("0.00")).quantize(Decimal("0.01"))
                staff_tip = sum((row["staff_tip_total"] for row in per_meal_service_rows), Decimal("0.00")).quantize(Decimal("0.01"))
                waiter_set = {row["wait_staff_count"] for row in per_meal_service_rows}
                waiter_value = waiter_set.pop() if len(waiter_set) == 1 else None
                tip_set = {row["staff_tip_per_waiter"] for row in per_meal_service_rows}
                tip_value = tip_set.pop() if len(tip_set) == 1 else None
                staff_context = {
                    "waiters": waiter_value if waiter_value is not None else waiters,
                    "waiters_varies": waiter_value is None,
                    "hours": staff_hours,
                    "hourly_rate": rate,
                    "labor_total": staff_pay,
                    "tip_per_waiter": Decimal("0.00") if estimate.client_tipped_at_event else tip_value,
                    "tip_total": staff_tip,
                    "grand": staff_pay + staff_tip,
                    "tip_varies": False if estimate.client_tipped_at_event else tip_value is None,
                    "per_meal": per_meal_service_rows,
                }
            else:
                staff_hours = estimate.staff_hours or Decimal("0.00")
                tip = estimate._get_staff_tip_per_waiter()
                staff_pay = (rate * staff_hours * waiters).quantize(Decimal("0.01"))
                staff_tip = Decimal("0.00")
                if not estimate.client_tipped_at_event:
                    staff_tip = (tip * waiters).quantize(Decimal("0.01"))
                staff_context = {
                    "waiters": waiters,
                    "waiters_varies": False,
                    "hours": staff_hours,
                    "hourly_rate": rate,
                    "labor_total": staff_pay,
                    "tip_per_waiter": Decimal("0.00") if estimate.client_tipped_at_event else tip,
                    "tip_total": staff_tip,
                    "grand": staff_pay + staff_tip,
                    "tip_varies": False,
                    "per_meal": [],
                }

        meal_sections = estimate.meal_sections()
        first_menu_item_count = 0
        if meal_sections:
            first_meal = meal_sections[0]
            first_menu_item_count = sum(
                len(category.get("choices", [])) for category in first_meal.get("categories", [])
            )
            first_menu_item_count += sum(
                len(category.get("choices", [])) for category in first_meal.get("kids_categories", [])
            )
        menu_compact_level = ""
        if first_menu_item_count >= 16:
            menu_compact_level = "tight"
        elif first_menu_item_count >= 13:
            menu_compact_level = "compact"
        meal_total_amount = (
            sum((section["total"] for section in meal_sections), Decimal("0.00"))
            if meal_sections
            else Decimal("0.00")
        )
        kids_total_amount = (
            sum((section.get("kids_total", Decimal("0.00")) for section in meal_sections), Decimal("0.00"))
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

        tablecloth_rows = estimate.tablecloth_rows()
        show_plasticware = bool(estimate.plasticware_color and not estimate.uses_real_dishes_anywhere())

        context = {
            "estimate": estimate,
            "meal_sections": meal_sections,
            "extra_lines": extra_lines,
            "extras_rows": extras_rows,
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
            "kids_total_amount": kids_total_amount,
            "service_style": service_style,
            "menu_compact_level": menu_compact_level,
            "contact_lines": [
                line for line in [
                    caterer.company_phone,
                    caterer.company_email,
                    caterer.company_address,
                ] if line
            ],
            "bank_details": caterer.bank_details,
            "flat_mode": False,
            "per_meal_service_rows": per_meal_service_rows,
            "delivery_fee": delivery_fee,
            "show_delivery_fee": show_delivery_fee,
            "dishes_delivery_fee": dishes_delivery_fee,
            "dishes_subtotal": dishes_subtotal,
            "tablecloth_rows": tablecloth_rows,
            "show_plasticware": show_plasticware,
        }
        return render(request, "admin/estimate_print.html", context)

    def print_estimate_flat(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        estimate.recalc_totals()
        extra_lines = (
            estimate.extra_lines.select_related("extra_item")
            .order_by("extra_item__category", "extra_item__name")
        )
        fx_rate = (estimate.exchange_rate or Decimal("1.00"))
        extras_rows = []
        for line in extra_lines:
            base_price = line.override_price if line.override_price is not None else line.extra_item.price
            display_price = None
            if base_price is not None:
                display_price = (base_price * fx_rate).quantize(Decimal("0.01"))
            extras_rows.append(
                {
                    "name": line.extra_item.name,
                    "quantity": line.quantity,
                    "notes": line.notes,
                    "charge_type": line.extra_item.get_charge_type_display(),
                    "price": display_price,
                    "is_included": display_price in (None, Decimal("0.00")),
                }
            )
        per_meal_service_rows = estimate.per_meal_service_summary()
        show_delivery_fee = any(row.get("wants_real_dishes") for row in per_meal_service_rows)
        delivery_fee = (
            estimate.real_dishes_flat_fee
            or (estimate.caterer.real_dishes_flat_fee if estimate.caterer_id else Decimal("0.00"))
            or Decimal("0.00")
        )
        caterer = estimate.caterer
        staff_context = None
        if not estimate.is_ala_carte:
            waiters = estimate.total_waiter_count()
            staff_hours = estimate.staff_hours or Decimal("0.00")
            rate = estimate._get_staff_hourly_rate()
            tip = estimate._get_staff_tip_per_waiter()
            staff_pay = (rate * staff_hours * waiters).quantize(Decimal("0.01"))
            staff_tip = Decimal("0.00")
            if not estimate.client_tipped_at_event:
                staff_tip = (tip * waiters).quantize(Decimal("0.01"))
            staff_context = {
                "waiters": waiters,
                "waiters_varies": False,
                "hours": staff_hours,
                "hourly_rate": rate,
                "labor_total": staff_pay,
                "tip_per_waiter": Decimal("0.00") if estimate.client_tipped_at_event else tip,
                "tip_total": staff_tip,
                "grand": staff_pay + staff_tip,
            }
        dishes_delivery_fee = Decimal("0.00")
        dishes_subtotal = estimate.dishes_total
        if estimate.dishes_total:
            dishes_delivery_fee = min(delivery_fee, estimate.dishes_total)
            dishes_subtotal = (estimate.dishes_total - dishes_delivery_fee).quantize(Decimal("0.01"))

        meal_sections = estimate.meal_sections()
        first_menu_item_count = 0
        if meal_sections:
            first_meal = meal_sections[0]
            first_menu_item_count = sum(
                len(category.get("choices", [])) for category in first_meal.get("categories", [])
            )
            first_menu_item_count += sum(
                len(category.get("choices", [])) for category in first_meal.get("kids_categories", [])
            )
        menu_compact_level = ""
        if first_menu_item_count >= 16:
            menu_compact_level = "tight"
        elif first_menu_item_count >= 13:
            menu_compact_level = "compact"
        meal_total_amount = (
            sum((section["total"] + section.get("kids_total", Decimal("0.00")) for section in meal_sections), Decimal("0.00"))
            if meal_sections
            else Decimal("0.00")
        )
        kids_total_amount = (
            sum((section.get("kids_total", Decimal("0.00")) for section in meal_sections), Decimal("0.00"))
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
        tablecloth_rows = estimate.tablecloth_rows()
        show_plasticware = bool(estimate.plasticware_color and not estimate.uses_real_dishes_anywhere())

        total_guests = (estimate.guest_count or 0) + (estimate.guest_count_kids or 0)
        per_person = Decimal("0.00")
        if total_guests:
            per_person = (estimate.grand_total / Decimal(total_guests)).quantize(Decimal("0.01"))
        flat_deposit_pct = Decimal("30.00")
        flat_deposit_amount = estimate.deposit_amount
        flat_deposit_pct = estimate.deposit_percentage or Decimal("30.00")
        flat_balance = estimate.balance_due

        context = {
            "estimate": estimate,
            "meal_sections": meal_sections,
            "extra_lines": extra_lines,
            "extras_rows": extras_rows,
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
            "kids_total_amount": kids_total_amount,
            "service_style": service_style,
            "menu_compact_level": menu_compact_level,
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
            "per_meal_service_rows": per_meal_service_rows,
            "delivery_fee": delivery_fee,
            "show_delivery_fee": show_delivery_fee,
            "dishes_delivery_fee": dishes_delivery_fee,
            "dishes_subtotal": dishes_subtotal,
            "tablecloth_rows": tablecloth_rows,
            "show_plasticware": show_plasticware,
        }
        return render(request, "admin/estimate_print.html", context)

    def _workflow_pages(self, request, estimate):
        """
        Build one payload per meal (page) so each meal prints separately.
        Meal ordering follows the planned meal list; ad-hoc meal names from choices
        are appended in alpha order.
        """

        def normalize(name: str, default: str) -> str:
            val = (name or default or "").strip()
            return val.lower()

        plan = estimate.get_meal_plan()
        default_meal = plan[0] if plan else estimate.default_meal_name()
        tablecloth_rows = estimate.tablecloth_rows()
        plasticware_value = estimate.plasticware_color if not estimate.uses_real_dishes_anywhere() else ""
        choices = list(
            estimate.food_choices.select_related("menu_item", "menu_item__category")
            .order_by(
                F("menu_item__category__sort_order").asc(nulls_last=True),
                F("menu_item__category__name").asc(nulls_last=True),
                F("menu_item__sort_order_override").asc(nulls_last=True),
                "menu_item__name",
            )
        )

        meal_display = {}
        meal_order_keys = []
        for name in plan:
            key = normalize(name, default_meal)
            if key not in meal_display:
                meal_order_keys.append(key)
            meal_display[key] = name

        choices_by_meal = {}
        seen_choice_keys = set()
        for choice in choices:
            meal_name = choice.meal_name or default_meal
            meal_key = normalize(meal_name, default_meal)
            seen_choice_keys.add(meal_key)
            meal_display.setdefault(meal_key, meal_name)
            meal_bucket = choices_by_meal.setdefault(meal_key, [])

            category = "Chef's Selection"
            order = 999
            if choice.menu_item and choice.menu_item.category:
                category = choice.menu_item.category.name
                order = choice.menu_item.category.sort_order or order

            meal_bucket.append(
                {
                    "item": choice.menu_item.name if choice.menu_item else "",
                    "notes": choice.notes,
                    "category": category,
                    "category_order": order,
                }
            )

        # Append any meals that appeared only in food choices (e.g., renamed meals)
        for key in sorted(seen_choice_keys):
            if key not in meal_order_keys:
                meal_order_keys.append(key)

        logo_url = None
        if estimate.caterer.brand_logo:
            logo_url = request.build_absolute_uri(estimate.caterer.brand_logo.url)

        pages = []
        for key in meal_order_keys or [normalize(default_meal, default_meal)]:
            display_name = meal_display.get(key, default_meal)
            meal_rows = choices_by_meal.get(key, [])

            # Group rows by category for this meal only.
            section_map = {}
            for row in meal_rows:
                cat_key = (row["category_order"], row["category"])
                section_map.setdefault(cat_key, []).append(row)

            meal_sections = []
            for (order, category), rows in sorted(section_map.items(), key=lambda x: (x[0][0], x[0][1])):
                meal_sections.append({"category": category, "items": rows})
            page_tablecloths = [row for row in tablecloth_rows if row.get("meal") == display_name]
            pages.append(
                {
                    "estimate": estimate,
                    "meal_name": display_name,
                    "sections": meal_sections,
                    "extras": [],
                    "logo_url": logo_url,
                    "primary_color": estimate.caterer.brand_primary_color or "#0f172a",
                    "accent_color": estimate.caterer.brand_accent_color or "#b08c6d",
                    "tablecloths": page_tablecloths,
                    "plasticware_color": plasticware_value,
                }
            )

        extras = list(
            estimate.extra_lines.select_related("extra_item").order_by("extra_item__category", "extra_item__name")
        )
        if pages and extras:
            pages[-1]["extras"] = extras

        return pages

    def workflow_view(self, request, estimate_id):
        estimate = self._get_estimate(estimate_id)
        if not request.user.is_superuser and estimate.caterer.owner != request.user:
            raise PermissionDenied("You do not have access to this estimate.")
        payload = self._workflow_pages(request, estimate)
        return render(
            request,
            "admin/estimate_workflow.html",
            {"workflows": payload, "auto_print": request.GET.get("print") == "1"},
        )

    def workflow_bulk_view(self, request):
        ids = request.GET.get("ids", "")
        id_list = [int(pk) for pk in ids.split(",") if pk.isdigit()]
        qs = Estimate.objects.select_related("caterer", "caterer__owner")
        if not request.user.is_superuser:
            qs = qs.filter(caterer__owner=request.user)
        if self.estimate_type:
            qs = qs.filter(estimate_type=self.estimate_type)
        estimates = list(qs.filter(pk__in=id_list).order_by("event_date"))
        if not estimates:
            self.message_user(
                request,
                "No estimates found for workflow printing.",
                level=messages.WARNING,
            )
            return redirect(self._admin_reverse("changelist"))
        payloads = []
        for estimate in estimates:
            payloads.extend(self._workflow_pages(request, estimate))
        return render(
            request,
            "admin/estimate_workflow.html",
            {"workflows": payloads, "auto_print": request.GET.get("print") == "1"},
        )

    def _create_inline_menu_items(self, request):
        if request.method != "POST":
            return []
        caterer_id = request.POST.get("caterer")
        if not caterer_id:
            return []
        try:
            caterer = CatererAccount.objects.get(pk=caterer_id)
        except CatererAccount.DoesNotExist:
            return []

        created = 0
        created_item_ids = []
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

            menu_item = MenuItem.objects.create(
                caterer=caterer,
                category=category,
                name=name,
                description=desc,
                cost_per_serving=cost,
                menu_type=self.menu_type,
                markup=markup,
                default_servings_per_person=servings,
                is_active=True,
            )
            created += 1
            created_item_ids.append(menu_item.id)

        if created:
            self.message_user(
                request,
                f"Added {created} new menu item(s) to the catalog for this caterer.",
                level=messages.SUCCESS,
            )
        return created_item_ids

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
        new_menu_item_ids = []
        if request.method == "POST":
            created_item_ids = self._create_inline_menu_items(request)
            if "_save_new_menu_item" in request.POST:
                new_menu_item_ids = created_item_ids

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
            if "_apply_meal_plan" in request.POST or "_save_new_menu_item" in request.POST:
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
        expense_entries = []
        expense_total = Decimal("0.00")
        staff_entries_manage_url = ""
        planner_sections = []
        planner_print_url = ""
        planner_missing_groups = []
        if obj and obj.pk:
            expense_entries = list(
                obj.expense_entries.select_related("created_by").order_by("-created_at")
            )
            for entry in expense_entries:
                if entry.expense_amount is not None:
                    expense_total += entry.expense_amount
            expense_total = expense_total.quantize(Decimal("0.01"))
            staff_entries_manage_url = (
                reverse("admin:client_estimates_estimatestafftimeentry_changelist")
                + f"?estimate__id__exact={obj.pk}&applied_to_expenses__exact=0"
            )
            planner_sections = self._planner_sections_for_estimate(obj)
            planner_missing_groups = self._planner_missing_groups_for_estimate(obj)
            planner_print_url = self._admin_reverse("planner_print", args=[obj.pk])
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
            "new_menu_item_ids": new_menu_item_ids,
            "preview_url_name": self._admin_url_name("print"),
            "expense_entries": expense_entries,
            "expense_total": expense_total,
            "expense_delete_url_name": f"admin:{self._admin_url_name('expense_delete')}",
            "staff_entries_manage_url": staff_entries_manage_url,
            "planner_sections": planner_sections,
            "planner_missing_groups": planner_missing_groups,
            "planner_print_url": planner_print_url,
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
                self._admin_reverse("change", args=[obj.pk])
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


@admin.register(KiddushEstimate)
class KiddushEstimateAdmin(EstimateAdmin):
    form = KiddushEstimateAdminForm
    estimate_type = "KIDDUSH"
    menu_type = "KIDDUSH"

    def _base_perm(self, request, action):
        return request.user.has_perm(f"{Estimate._meta.app_label}.{action}_estimate")

    def get_model_perms(self, request):
        if request.user.is_superuser:
            return super().get_model_perms(request)
        return {
            "add": self._base_perm(request, "add"),
            "change": self._base_perm(request, "change"),
            "delete": self._base_perm(request, "delete"),
            "view": self._base_perm(request, "view") or self._base_perm(request, "change"),
        }

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return self._base_perm(request, "add")

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return self._base_perm(request, "change")

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return self._base_perm(request, "view") or self._base_perm(request, "change")

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return self._base_perm(request, "delete")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("event_type", "Kiddush")
        return initial

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        ensure_kiddush_planning_fee_line(obj)
        obj.save()

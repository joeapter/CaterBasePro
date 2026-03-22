import logging
import json
import time
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

from django import forms
from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.core.mail import send_mail
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import stripe

from .forms import ClientInquiryForm
from .models import (
    CatererAccount,
    CatererUserAccess,
    ExtraItem,
    Estimate,
    EstimateExtraItem,
    EstimateFoodChoice,
    MenuItem,
    EstimatePlannerEntry,
    EstimateExpenseEntry,
    EstimateStaffTimeEntry,
    PAYMENT_METHOD_CHOICES,
    PlasticwareOption,
    PlannerFieldCard,
    PlannerFieldMemory,
    PlannerOptionCard,
    PlannerOptionIcon,
    PLANNER_SECTION_CHOICES,
    ShoppingList,
    ShoppingListItem,
    STAFF_ROLE_CHOICES,
    SHOPPING_CATEGORY_CHOICES,
    TableclothOption,
    TrialRequest,
    XpenzMobileToken,
)

logger = logging.getLogger(__name__)
User = get_user_model()

STAFF_ROLE_RATES = {
    "KITCHEN": Decimal("50.00"),
    "WAIT": Decimal("40.00"),
    "MANAGEMENT": Decimal("60.00"),
}
STAFF_PUNCH_TOKEN_SALT = "xpenz-staff-punch"
SHOPPING_CATEGORY_ORDER = {
    code: index for index, (code, _label) in enumerate(SHOPPING_CATEGORY_CHOICES)
}
SHOPPING_CATEGORY_LABELS = {code: label for code, label in SHOPPING_CATEGORY_CHOICES}
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

PRODUCE_KEYWORDS = {
    "produce",
    "tomato",
    "lettuce",
    "onion",
    "garlic",
    "mushroom",
    "cucumber",
    "pepper",
    "carrot",
    "potato",
    "spinach",
    "parsley",
    "cilantro",
    "oregano",
    "basil",
    "thyme",
    "mint",
    "apple",
    "banana",
    "lemon",
    "lime",
    "orange",
    "avocado",
}
MEAT_POULTRY_FISH_KEYWORDS = {
    "chicken",
    "beef",
    "steak",
    "lamb",
    "veal",
    "turkey",
    "duck",
    "fish",
    "salmon",
    "tuna",
    "brisket",
    "ground",
    "mince",
    "meat",
}
DAIRY_EGG_KEYWORDS = {
    "milk",
    "cheese",
    "yogurt",
    "yoghurt",
    "cream",
    "butter",
    "egg",
    "eggs",
}
PANTRY_KEYWORDS = {
    "rice",
    "pasta",
    "flour",
    "sugar",
    "salt",
    "spice",
    "oil",
    "vinegar",
    "beans",
    "lentils",
    "quinoa",
    "canned",
    "can",
    "jar",
    "jars",
    "pesto",
    "sauce",
}
BAKERY_KEYWORDS = {"bread", "bagel", "challah", "bun", "roll", "pita", "baguette", "cake"}
FROZEN_KEYWORDS = {"frozen", "ice", "fries"}
BEVERAGE_KEYWORDS = {"water", "soda", "juice", "wine", "beer", "drink", "cola"}
DISPOSABLE_KEYWORDS = {
    "plate",
    "plates",
    "cup",
    "cups",
    "napkin",
    "napkins",
    "fork",
    "forks",
    "knife",
    "knives",
    "spoon",
    "spoons",
    "tray",
    "trays",
    "foil",
    "container",
    "containers",
}
DEFAULT_SHOPPING_UNIT_OPTIONS = ("Kg", "Pieces", "Cans")


class TrialSignupForm(forms.Form):
    name = forms.CharField(max_length=200)
    company_name = forms.CharField(max_length=200)
    email = forms.EmailField()
    phone = forms.CharField(max_length=50, required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("password")
        pwd2 = cleaned.get("password_confirm")
        if pwd and pwd2 and pwd != pwd2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


def marketing_home(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        notes = (request.POST.get("notes") or "").strip()

        if not name:
            messages.error(request, "Please add your name to start the 30-day trial.")
            return redirect(reverse("marketing_home") + "#cta")

        trial = TrialRequest.objects.create(
            name=name,
            email=email,
            phone=phone,
            notes=notes,
        )

        notify_email = getattr(settings, "TRIAL_NOTIFY_EMAIL", "")
        if notify_email:
            subject = f"New 30-day trial request: {trial.name}"
            body_lines = [
                f"Name: {trial.name}",
                f"Email: {trial.email}",
                f"Phone: {trial.phone}",
                "",
                "Notes:",
                trial.notes or "(none)",
            ]
            try:
                send_mail(
                    subject=subject,
                    message="\n".join(body_lines),
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[notify_email],
                    fail_silently=True,
                )
            except Exception:
                logger.exception("Failed to send trial notification email.")

        messages.success(
            request,
            "Thanks! Your 30-day trial request is in. We’ll reach out shortly to finish setup.",
        )
        return redirect(reverse("marketing_home") + "#cta")

    return render(request, "marketing/landing.html")


def start_trial(request):
    if request.method == "POST":
        form = TrialSignupForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.create_user(
                username=email,
                email=email,
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["name"],
                is_staff=True,
                is_active=True,
            )
            CatererAccount.objects.create(
                name=form.cleaned_data["company_name"],
                owner=user,
                primary_contact_name=form.cleaned_data["name"],
                company_email=email,
                company_phone=form.cleaned_data.get("phone", ""),
            )
            messages.success(request, "Welcome! Your 30-day trial has started.")
            login(request, user)
            return redirect("/admin/")
    else:
        form = TrialSignupForm()
    return render(request, "marketing/start_trial.html", {"form": form})


def trial_expired(request):
    payment_url = getattr(settings, "TRIAL_PAYMENT_URL", "")
    return render(request, "marketing/trial_expired.html", {"payment_url": payment_url})


def _get_caterer_from_host(request):
    base_domain = getattr(settings, "PUBLIC_BASE_DOMAIN", "")
    host = request.get_host().split(":")[0].lower()
    if not base_domain:
        return None
    if host == base_domain or host == f"www.{base_domain}":
        return None
    if host.endswith(f".{base_domain}"):
        slug = host[: -len(base_domain) - 1]
        if slug and slug not in {"www"}:
            return CatererAccount.objects.filter(slug=slug).first()
    return None


def new_client_inquiry(request, caterer_slug=None):
    caterer = None
    if caterer_slug:
        caterer = get_object_or_404(CatererAccount, slug=caterer_slug)
    else:
        caterer = _get_caterer_from_host(request)
        if not caterer:
            raise Http404("No caterer matched this inquiry link.")

    if request.method == "POST":
        form = ClientInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.caterer = caterer
            inquiry.save()
            messages.success(
                request,
                "Thanks for reaching out! We'll respond shortly.",
            )
            return redirect(
                reverse(
                    "public_inquiry",
                    kwargs={"caterer_slug": caterer.slug},
                )
            )
    else:
        form = ClientInquiryForm()

    return render(
        request,
        "public/new_client_inquiry.html",
        {
            "form": form,
            "caterer": caterer,
        },
    )


# Stripe webhook endpoint
stripe.api_key = settings.STRIPE_SECRET_KEY or ""


@csrf_exempt
def stripe_webhook(request):
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.error("Stripe webhook received but STRIPE_WEBHOOK_SECRET is not set.")
        return HttpResponse("Webhook secret not configured", status=500)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )
    except ValueError:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return HttpResponse(status=400)

    event_type = event.get("type")
    event_obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        logger.info("Stripe checkout.session.completed id=%s", event_obj.get("id"))
    elif event_type == "invoice.paid":
        logger.info("Stripe invoice.paid id=%s", event_obj.get("id"))
    elif event_type == "invoice.payment_failed":
        logger.warning("Stripe invoice.payment_failed id=%s", event_obj.get("id"))
    elif event_type == "customer.subscription.created":
        logger.info("Stripe customer.subscription.created id=%s", event_obj.get("id"))
    elif event_type == "customer.subscription.updated":
        logger.info("Stripe customer.subscription.updated id=%s", event_obj.get("id"))
    elif event_type == "customer.subscription.deleted":
        logger.info("Stripe customer.subscription.deleted id=%s", event_obj.get("id"))
    else:
        logger.info("Unhandled Stripe event type=%s", event_type)

    return JsonResponse({"received": True})


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


_MOBILE_MEAL_CARD_RE = re.compile(
    r'(<article class="(?P<class>[^"]*\bmeal-card\b[^"]*)">)(?P<body>.*?)(</article>)',
    re.DOTALL,
)


def _apply_mobile_meal_density_compaction(html):
    """
    Apply compact/tight meal-card class by per-card menu item count.
    This mirrors the admin intent (auto compact when list is long) but
    runs per page for mobile PDF output.
    """

    def _compact_match(match):
        class_attr = match.group("class") or ""
        body = match.group("body") or ""
        li_count = body.count("<li")
        next_classes = class_attr
        if li_count >= 16:
            if "meal-card--tight" not in next_classes:
                next_classes = f"{next_classes} meal-card--tight".strip()
        elif li_count >= 13:
            if "meal-card--compact" not in next_classes and "meal-card--tight" not in next_classes:
                next_classes = f"{next_classes} meal-card--compact".strip()
        if next_classes == class_attr:
            return match.group(0)
        return f'<article class="{next_classes}">{body}</article>'

    return _MOBILE_MEAL_CARD_RE.sub(_compact_match, html)


def _clamp_mobile_print_html(response):
    """
    Enforce A4-safe print layout for the mobile print-html endpoint only.
    We keep admin template rules, but force print media rules to apply during
    Expo HTML->PDF rendering and lock sheet/page dimensions.
    """
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        return response

    encoding = response.charset or "utf-8"
    try:
        html = response.content.decode(encoding, errors="ignore")
    except Exception:
        return response

    html = _apply_mobile_meal_density_compaction(html)

    if "@media print" in html:
        html = html.replace("@media print", "@media all")

    if 'id="xpenz-mobile-print-clamp"' not in html:
        clamp_style = """
<style id="xpenz-mobile-print-clamp">
  @page {
    size: A4 !important;
    margin: 0 !important;
  }
  html, body {
    margin: 0 !important;
    padding: 0 !important;
    width: 210mm !important;
  }
  .estimate-sheet,
  .sheet {
    box-sizing: border-box !important;
    width: 210mm !important;
    min-height: 297mm !important;
    margin: 0 !important;
    page-break-after: always !important;
    break-after: page !important;
    page-break-inside: avoid !important;
    break-inside: avoid-page !important;
  }
  .estimate-sheet:last-of-type,
  .sheet:last-of-type {
    page-break-after: auto !important;
    break-after: auto !important;
  }
  .estimate-sheet[class*="sheet-bg--"] {
    background-repeat: no-repeat !important;
    background-size: cover !important;
    background-position: center top !important;
    background-attachment: local !important;
  }
</style>
"""
        if "</head>" in html:
            html = html.replace("</head>", f"{clamp_style}</head>", 1)
        else:
            html = f"{clamp_style}{html}"

    response.content = html.encode(encoding)
    response["Content-Length"] = str(len(response.content))
    return response


def _xpenz_authenticated_user(request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token_key = auth_header.split(" ", 1)[1].strip()
    if not token_key:
        return None
    token = XpenzMobileToken.objects.select_related("user").filter(key=token_key).first()
    if not token or not token.user.is_active:
        return None
    token.last_used_at = timezone.now()
    token.save(update_fields=["last_used_at"])
    return token.user


def _mobile_access_map_for_user(user):
    if user.is_superuser:
        return {"__superuser__": True}

    owner_caterer_ids = set(
        CatererAccount.objects.filter(owner=user).values_list("id", flat=True)
    )
    access_rows = list(
        CatererUserAccess.objects.select_related("caterer")
        .filter(
            user=user,
            is_active=True,
            can_access_mobile_app=True,
        )
    )

    access_map = {}
    for caterer_id in owner_caterer_ids:
        access_map[caterer_id] = {
            "is_owner": True,
            "can_access_mobile_app": True,
            "can_add_expenses": True,
            "can_view_job_billing": True,
            "can_manage_staff": True,
        }

    for row in access_rows:
        if row.caterer_id in access_map and access_map[row.caterer_id]["is_owner"]:
            continue
        access_map[row.caterer_id] = {
            "is_owner": False,
            "can_access_mobile_app": bool(row.can_access_mobile_app),
            "can_add_expenses": bool(row.can_add_expenses),
            "can_view_job_billing": bool(row.can_view_job_billing),
            "can_manage_staff": bool(row.can_manage_staff),
        }
    return access_map


def _mobile_access_for_caterer(user, caterer_id, access_map=None):
    if user.is_superuser:
        return {
            "is_owner": True,
            "can_access_mobile_app": True,
            "can_add_expenses": True,
            "can_view_job_billing": True,
            "can_manage_staff": True,
        }
    access_map = access_map or _mobile_access_map_for_user(user)
    return access_map.get(caterer_id)


def _can_access_estimate(user, estimate, access_map=None):
    return bool(_mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map))


def _can_add_expenses(user, estimate, access_map=None):
    access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
    return bool(access and access.get("can_add_expenses"))


def _can_manage_staff(user, estimate, access_map=None):
    access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
    return bool(access and access.get("can_manage_staff"))


def _can_edit_estimate_mobile(user, estimate, access_map=None):
    if user.is_superuser:
        return True
    access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
    if not access:
        return False
    if access.get("is_owner"):
        return True
    return bool(access.get("can_view_job_billing"))


def _to_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_decimal_string(value, default=""):
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _serialize_expense_entry(request, entry):
    receipt_url = ""
    voice_url = ""
    if entry.receipt_image:
        receipt_url = request.build_absolute_uri(entry.receipt_image.url)
    if entry.voice_note:
        voice_url = request.build_absolute_uri(entry.voice_note.url)
    return {
        "id": entry.id,
        "expense_text": entry.expense_text,
        "expense_amount": str(entry.expense_amount) if entry.expense_amount is not None else "",
        "is_manual_only": entry.is_manual_only,
        "note_text": entry.note_text,
        "voice_note_duration_seconds": entry.voice_note_duration_seconds,
        "created_at": entry.created_at.isoformat(),
        "created_by": entry.created_by.get_username() if entry.created_by else "",
        "receipt_image_url": receipt_url,
        "voice_note_url": voice_url,
        "has_receipt_image": bool(entry.receipt_image),
        "has_voice_note": bool(entry.voice_note),
    }


def _serialize_staff_entry(entry):
    return {
        "id": entry.id,
        "role": entry.role,
        "role_label": entry.get_role_display(),
        "worker_first_name": entry.worker_first_name,
        "hourly_rate": str(entry.hourly_rate),
        "punched_in_at": entry.punched_in_at.isoformat() if entry.punched_in_at else "",
        "punched_out_at": entry.punched_out_at.isoformat() if entry.punched_out_at else "",
        "total_hours": str(entry.total_hours or Decimal("0.00")),
        "total_cost": str(entry.total_cost or Decimal("0.00")),
        "applied_to_expenses": bool(entry.applied_to_expenses),
        "expense_entry_id": entry.expense_entry_id,
    }


def _serialize_mobile_estimate(request, user, estimate, access_map=None):
    event_type = (estimate.event_type or "Event").strip()
    access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
    can_view_billing = bool(access and access.get("can_view_job_billing"))
    can_add_expenses = bool(access and access.get("can_add_expenses"))
    can_manage_staff = bool(access and access.get("can_manage_staff"))
    if user.is_superuser:
        can_view_billing = True
        can_add_expenses = True
        can_manage_staff = True

    estimate_print_url = request.build_absolute_uri(
        reverse("admin:client_estimates_estimate_print", args=[estimate.id])
    )
    estimate_print_flat_url = request.build_absolute_uri(
        reverse("admin:client_estimates_estimate_print_flat", args=[estimate.id])
    )
    planner_print_url = request.build_absolute_uri(
        reverse("admin:client_estimates_estimate_planner_print", args=[estimate.id])
    )
    workflow_print_url = request.build_absolute_uri(
        reverse("admin:client_estimates_estimate_workflow", args=[estimate.id])
    )

    return {
        "id": estimate.id,
        "estimate_number": estimate.estimate_number,
        "job_name": f"{estimate.customer_name} - {event_type}",
        "customer_name": estimate.customer_name,
        "event_type": estimate.event_type,
        "event_date": estimate.event_date.isoformat() if estimate.event_date else "",
        "event_location": estimate.event_location,
        "guest_count": estimate.guest_count,
        "guest_count_kids": estimate.guest_count_kids,
        "caterer_id": estimate.caterer_id,
        "caterer_name": estimate.caterer.name if estimate.caterer_id else "",
        "currency": estimate.currency,
        "grand_total": _to_decimal_string(estimate.grand_total) if can_view_billing else "",
        "expense_count": int(getattr(estimate, "expense_count", 0) or 0),
        "can_view_billing": can_view_billing,
        "can_add_expenses": can_add_expenses,
        "can_manage_staff": can_manage_staff,
        "print_urls": {
            "estimate": estimate_print_url,
            "estimate_print": f"{estimate_print_url}?print=1",
            "estimate_flat": estimate_print_flat_url,
            "estimate_flat_print": f"{estimate_print_flat_url}?print=1",
            "planner": planner_print_url,
            "planner_print": f"{planner_print_url}?print=1",
            "workflow": workflow_print_url,
            "workflow_print": f"{workflow_print_url}?print=1",
        },
    }


def _staff_punch_token_payload(estimate_id, role):
    return {
        "estimate_id": int(estimate_id),
        "role": str(role),
    }


def _build_staff_punch_token(estimate_id, role):
    return signing.dumps(
        _staff_punch_token_payload(estimate_id, role),
        salt=STAFF_PUNCH_TOKEN_SALT,
    )


def _load_staff_punch_token(token):
    return signing.loads(
        token,
        salt=STAFF_PUNCH_TOKEN_SALT,
        max_age=60 * 60 * 24 * 120,
    )


def _staff_role_rows_for_estimate(request, estimate):
    rows = []
    for role_code, role_label in STAFF_ROLE_CHOICES:
        token = _build_staff_punch_token(estimate.id, role_code)
        punch_url = request.build_absolute_uri(
            reverse("xpenz_staff_punch", kwargs={"token": token})
        )
        qr_data = quote_plus(punch_url)
        rows.append(
            {
                "code": role_code,
                "label": role_label,
                "hourly_rate": str(STAFF_ROLE_RATES.get(role_code, Decimal("0.00"))),
                "punch_url": punch_url,
                "qr_image_url": f"https://api.qrserver.com/v1/create-qr-code/?size=360x360&data={qr_data}",
            }
        )
    return rows


def _normalize_item_text(value):
    return " ".join((value or "").strip().split())


def _merge_option_values(*groups):
    seen = set()
    merged = []
    for group in groups:
        for raw_value in group or []:
            value = _normalize_item_text(raw_value)
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(value)
    return merged


def _parse_quantity(value):
    raw = _normalize_item_text(value)
    if not raw:
        return Decimal("1.00")
    try:
        quantity = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if quantity <= Decimal("0.00"):
        return None
    return quantity.quantize(Decimal("0.01"))


def _infer_shopping_category(item_name):
    words = set(_normalize_item_text(item_name).lower().replace("-", " ").split())
    if not words:
        return "OTHER"
    if words & PRODUCE_KEYWORDS:
        return "PRODUCE"
    if words & MEAT_POULTRY_FISH_KEYWORDS:
        return "MEAT_POULTRY_FISH"
    if words & DAIRY_EGG_KEYWORDS:
        return "DAIRY_EGGS"
    if words & BAKERY_KEYWORDS:
        return "BAKERY"
    if words & FROZEN_KEYWORDS:
        return "FROZEN"
    if words & BEVERAGE_KEYWORDS:
        return "BEVERAGES"
    if words & DISPOSABLE_KEYWORDS:
        return "DISPOSABLES"
    if words & PANTRY_KEYWORDS:
        return "PANTRY"
    return "OTHER"


def _historical_shopping_category(caterer_id, item_name):
    normalized_item_name = _normalize_item_text(item_name)
    if not caterer_id or not normalized_item_name:
        return ""

    counts = {}
    rows = ShoppingListItem.objects.filter(
        shopping_list__caterer_id=caterer_id,
        item_name__iexact=normalized_item_name,
    ).values_list("category", flat=True)
    for code in rows:
        if not code:
            continue
        counts[code] = counts.get(code, 0) + 1

    if not counts:
        return ""

    return sorted(
        counts.items(),
        key=lambda part: (-part[1], SHOPPING_CATEGORY_ORDER.get(part[0], 999), part[0]),
    )[0][0]


def _resolve_shopping_category(caterer_id, item_name):
    saved_category = _historical_shopping_category(caterer_id, item_name)
    if saved_category:
        return saved_category
    return _infer_shopping_category(item_name)


def _format_quantity(quantity):
    quantized = (quantity or Decimal("0.00")).quantize(Decimal("0.01"))
    as_string = f"{quantized}"
    if as_string.endswith(".00"):
        return as_string[:-3]
    if as_string.endswith("0"):
        return as_string[:-1]
    return as_string


def _serialize_shopping_list_entry(entry):
    estimate_label = ""
    if entry.estimate_id:
        est_num = f"#{entry.estimate.estimate_number}" if entry.estimate and entry.estimate.estimate_number else ""
        est_name = entry.estimate.customer_name if entry.estimate else ""
        estimate_label = " ".join([part for part in [est_num, est_name] if part]).strip()
    return {
        "id": entry.id,
        "title": entry.title or f"Shopping List #{entry.id}",
        "caterer_id": entry.caterer_id,
        "caterer_name": entry.caterer.name if entry.caterer_id else "",
        "estimate_id": entry.estimate_id,
        "estimate_label": estimate_label,
        "item_count": getattr(entry, "item_count", 0),
        "is_deleted": bool(entry.deleted_at),
        "execution_started_at": entry.execution_started_at.isoformat() if entry.execution_started_at else "",
        "execution_started_by": (
            entry.execution_started_by.get_username()
            if getattr(entry, "execution_started_by", None)
            else ""
        ),
        "created_by": entry.created_by.get_username() if entry.created_by else "",
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
    }


def _serialize_shopping_item(entry):
    return {
        "id": entry.id,
        "item_name": entry.item_name,
        "item_type": entry.item_type,
        "item_unit": entry.item_unit,
        "quantity": _format_quantity(entry.quantity),
        "category": entry.category,
        "category_label": entry.get_category_display(),
        "collaboration_note": (entry.collaboration_note or "").lower(),
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
    }


def _humanize_code(value):
    raw = (value or "").strip().replace("_", " ").replace("-", " ")
    if not raw:
        return ""
    return " ".join(part.capitalize() for part in raw.split())


def _planner_group_label(section, group_code):
    return PLANNER_GROUP_LABELS.get((section, group_code), _humanize_code(group_code))


def _planner_item_label(section, group_code, item_code):
    if not item_code:
        return ""
    return PLANNER_ITEM_LABELS.get((section, group_code, item_code), _humanize_code(item_code))


def _planner_field_label(field_code):
    if field_code in PLANNER_FIELD_LABELS:
        return PLANNER_FIELD_LABELS[field_code]
    return _humanize_code(field_code)


def _serialize_planner_entry(entry):
    data_rows = []
    for key, value in (entry.data or {}).items():
        data_rows.append(
            {
                "field_code": key,
                "field_label": _planner_field_label(key),
                "value": value,
            }
        )
    data_rows.sort(key=lambda row: row["field_label"].lower())
    return {
        "id": entry.id,
        "estimate_id": entry.estimate_id,
        "section": entry.section,
        "section_label": PLANNER_SECTION_LABELS.get(entry.section, entry.section),
        "group_code": entry.group_code,
        "group_label": _planner_group_label(entry.section, entry.group_code),
        "item_code": entry.item_code,
        "item_label": _planner_item_label(entry.section, entry.group_code, entry.item_code),
        "data": entry.data or {},
        "data_rows": data_rows,
        "notes": entry.notes or "",
        "is_checked": bool(entry.is_checked),
        "sort_order": entry.sort_order or 0,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
    }


def _planner_memory_payload(memory_rows):
    grouped = {}
    for row in memory_rows:
        key = (row.section, row.group_code or "", row.item_code or "", row.field_code or "")
        grouped.setdefault(key, []).append(row.value)

    payload = []
    for (section, group_code, item_code, field_code), values in grouped.items():
        payload.append(
            {
                "section": section,
                "group_code": group_code,
                "item_code": item_code,
                "field_code": field_code,
                "values": _merge_option_values(values),
            }
        )
    payload.sort(
        key=lambda row: (
            row["section"],
            row["group_code"],
            row["item_code"],
            row["field_code"],
        )
    )
    return payload


def _planner_field_card_payload(caterer_id):
    if not caterer_id:
        return []
    rows = (
        PlannerFieldCard.objects.filter(caterer_id=caterer_id)
        .order_by("section", "group_code", "item_code", "sort_order", "field_label")
    )
    payload = []
    for row in rows:
        payload.append(
            {
                "section": row.section,
                "group_code": row.group_code or "",
                "item_code": row.item_code or "",
                "field_code": row.field_code or "",
                "field_label": row.field_label or _planner_field_label(row.field_code),
                "value_options": _merge_option_values(row.value_options or []),
                "sort_order": int(row.sort_order or 0),
            }
        )
    return payload


def _planner_item_catalog_payload(caterer_id):
    if not caterer_id:
        return []

    catalog_map = {}
    option_rows = (
        PlannerOptionCard.objects.filter(caterer_id=caterer_id)
        .order_by("section", "group_code", "sort_order", "item_label", "item_code")
    )
    for row in option_rows:
        section = row.section or ""
        group_code = row.group_code or ""
        item_code = row.item_code or ""
        if not section or not group_code or not item_code:
            continue
        key = (section, group_code, item_code)
        catalog_map[key] = {
            "section": section,
            "group_code": group_code,
            "item_code": item_code,
            "item_label": _normalize_item_text(row.item_label)
            or _planner_item_label(section, group_code, item_code),
            "usage_count": 0,
            "sort_order": int(row.sort_order or 0),
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
        if key not in catalog_map:
            catalog_map[key] = {
                "section": section,
                "group_code": group_code,
                "item_code": item_code,
                "item_label": _planner_item_label(section, group_code, item_code),
                "usage_count": 0,
                "sort_order": 9999,
            }
        catalog_map[key]["usage_count"] = int(catalog_map[key]["usage_count"]) + int(
            row.get("usage_count") or 0
        )
        if not _normalize_item_text(catalog_map[key].get("item_label")):
            catalog_map[key]["item_label"] = _planner_item_label(section, group_code, item_code)

    payload = list(catalog_map.values())
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


def _save_planner_option_card(
    estimate,
    section,
    group_code,
    item_code,
    item_label,
    sort_order,
    user,
):
    if not estimate.caterer_id:
        return None

    normalized_group = _normalize_item_text(group_code).replace(" ", "_").lower()
    normalized_item = _normalize_item_text(item_code).replace(" ", "_").lower()
    if not normalized_group or not normalized_item:
        return None

    cleaned_label = _normalize_item_text(item_label)
    if not cleaned_label:
        cleaned_label = _planner_item_label(section, normalized_group, normalized_item)

    try:
        normalized_sort_order = int(sort_order)
    except (TypeError, ValueError):
        normalized_sort_order = None
    if normalized_sort_order is None or normalized_sort_order < 0:
        existing_count = PlannerOptionCard.objects.filter(
            caterer_id=estimate.caterer_id,
            section=section,
            group_code=normalized_group,
        ).count()
        normalized_sort_order = existing_count

    option_card, _created = PlannerOptionCard.objects.get_or_create(
        caterer=estimate.caterer,
        section=section,
        group_code=normalized_group,
        item_code=normalized_item,
        defaults={
            "item_label": cleaned_label,
            "sort_order": normalized_sort_order,
            "updated_by": user,
        },
    )

    changed_fields = []
    if option_card.item_label != cleaned_label:
        option_card.item_label = cleaned_label
        changed_fields.append("item_label")
    if option_card.sort_order != normalized_sort_order:
        option_card.sort_order = normalized_sort_order
        changed_fields.append("sort_order")
    if option_card.updated_by_id != user.id:
        option_card.updated_by = user
        changed_fields.append("updated_by")
    if changed_fields:
        changed_fields.append("updated_at")
        option_card.save(update_fields=changed_fields)

    return {
        "section": option_card.section,
        "group_code": option_card.group_code or "",
        "item_code": option_card.item_code or "",
        "item_label": option_card.item_label or _planner_item_label(
            option_card.section, option_card.group_code, option_card.item_code
        ),
        "sort_order": int(option_card.sort_order or 0),
    }


def _planner_icon_override_payload(caterer_id):
    if not caterer_id:
        return []
    rows = (
        PlannerOptionIcon.objects.filter(caterer_id=caterer_id)
        .order_by("section", "group_code", "item_code")
    )
    payload = []
    for row in rows:
        payload.append(
            {
                "section": row.section,
                "group_code": row.group_code or "",
                "item_code": row.item_code or "",
                "icon_key": row.icon_key or "circle",
                "is_manual_override": bool(row.is_manual_override),
            }
        )
    return payload


def _planner_split_value_options(raw_value):
    value = _normalize_item_text(raw_value)
    if not value:
        return []
    normalized = value.replace("\n", ",").replace(";", ",")
    parts = []
    for chunk in normalized.split(","):
        cleaned = _normalize_item_text(chunk)
        if cleaned:
            parts.append(cleaned)
    if not parts:
        return [value]
    return _merge_option_values(parts)[:30]


def _record_planner_memory(estimate, section, group_code, item_code, data):
    if not estimate.caterer_id or not isinstance(data, dict):
        return
    for raw_field, raw_value in data.items():
        field_code = _normalize_item_text(raw_field)
        if not field_code:
            continue
        field_code = field_code.replace(" ", "_").lower()
        values = _planner_split_value_options(raw_value)
        if not values:
            continue
        for value in values:
            obj, created = PlannerFieldMemory.objects.get_or_create(
                caterer_id=estimate.caterer_id,
                section=section,
                group_code=_normalize_item_text(group_code).replace(" ", "_").lower(),
                item_code=_normalize_item_text(item_code).replace(" ", "_").lower(),
                field_code=field_code,
                value_key=value.lower(),
                defaults={"value": value, "usage_count": 1},
            )
            if created:
                continue
            changed_fields = []
            if obj.value != value:
                obj.value = value
                changed_fields.append("value")
            obj.usage_count = (obj.usage_count or 0) + 1
            changed_fields.append("usage_count")
            changed_fields.append("last_used_at")
            obj.save(update_fields=changed_fields)


def _save_planner_field_cards(
    estimate,
    section,
    group_code,
    item_code,
    payload_rows,
    user,
):
    if not estimate.caterer_id:
        return []

    normalized_group = _normalize_item_text(group_code).replace(" ", "_").lower()
    normalized_item = _normalize_item_text(item_code).replace(" ", "_").lower()
    existing = {
        row.field_code: row
        for row in PlannerFieldCard.objects.filter(
            caterer_id=estimate.caterer_id,
            section=section,
            group_code=normalized_group,
            item_code=normalized_item,
        )
    }

    kept_codes = []
    if not isinstance(payload_rows, list):
        payload_rows = []

    for index, raw_row in enumerate(payload_rows):
        if not isinstance(raw_row, dict):
            continue
        raw_label = _normalize_item_text(raw_row.get("field_label") or raw_row.get("label"))
        raw_code = _normalize_item_text(raw_row.get("field_code"))
        if not raw_code and raw_label:
            raw_code = raw_label.replace(" ", "_").lower()
        field_code = raw_code.replace(" ", "_").lower()
        field_code = "_".join(part for part in field_code.split("_") if part)
        if not field_code:
            continue
        field_label = raw_label or _planner_field_label(field_code)
        options = []
        for raw_value in raw_row.get("value_options") or []:
            options.extend(_planner_split_value_options(raw_value))
        if isinstance(raw_row.get("value_options_text"), str):
            options.extend(_planner_split_value_options(raw_row.get("value_options_text")))
        if isinstance(raw_row.get("values"), str):
            options.extend(_planner_split_value_options(raw_row.get("values")))
        options = _merge_option_values(options)[:40]
        sort_order = raw_row.get("sort_order")
        try:
            sort_order = int(sort_order)
        except (TypeError, ValueError):
            sort_order = index
        if sort_order < 0:
            sort_order = index

        card = existing.get(field_code)
        if not card:
            card = PlannerFieldCard(
                caterer=estimate.caterer,
                section=section,
                group_code=normalized_group,
                item_code=normalized_item,
                field_code=field_code,
            )
        card.field_label = field_label
        card.value_options = options
        card.sort_order = sort_order
        card.updated_by = user
        card.save()
        kept_codes.append(field_code)

    for field_code, row in existing.items():
        if field_code in kept_codes:
            continue
        row.delete()

    rows = (
        PlannerFieldCard.objects.filter(
            caterer_id=estimate.caterer_id,
            section=section,
            group_code=normalized_group,
            item_code=normalized_item,
        )
        .order_by("sort_order", "field_label")
    )
    return [
        {
            "section": row.section,
            "group_code": row.group_code or "",
            "item_code": row.item_code or "",
            "field_code": row.field_code or "",
            "field_label": row.field_label or _planner_field_label(row.field_code),
            "value_options": _merge_option_values(row.value_options or []),
            "sort_order": int(row.sort_order or 0),
        }
        for row in rows
    ]



def _build_shopping_catalog_queryset(user, access_map):
    rows = ShoppingListItem.objects.select_related("shopping_list", "shopping_list__caterer")
    if not user.is_superuser:
        rows = rows.filter(shopping_list__caterer_id__in=list(access_map.keys()))
    return rows.order_by("-updated_at", "-created_at", "-id")


def _shopping_catalog_payload(rows):
    grouped = {}
    for row in rows:
        item_name = _normalize_item_text(row.item_name)
        if not item_name:
            continue
        key = item_name.lower()
        if key not in grouped:
            grouped[key] = {
                "item_name": item_name,
                "usage_count": 0,
                "category_counts": {},
                "type_options": set(),
                "unit_options": set(),
                "last_used_unit": "",
            }
        bucket = grouped[key]
        bucket["usage_count"] += 1

        category_code = row.category or _infer_shopping_category(item_name)
        bucket["category_counts"][category_code] = bucket["category_counts"].get(category_code, 0) + 1

        item_type = _normalize_item_text(row.item_type)
        if item_type:
            bucket["type_options"].add(item_type)
        item_unit = _normalize_item_text(row.item_unit)
        if item_unit:
            bucket["unit_options"].add(item_unit)
            if not bucket["last_used_unit"]:
                bucket["last_used_unit"] = item_unit

    items = []
    for bucket in grouped.values():
        category_counts = bucket["category_counts"]
        if category_counts:
            category_code = sorted(
                category_counts.items(),
                key=lambda part: (-part[1], SHOPPING_CATEGORY_ORDER.get(part[0], 999), part[0]),
            )[0][0]
        else:
            category_code = _infer_shopping_category(bucket["item_name"])
        items.append(
            {
                "item_name": bucket["item_name"],
                "usage_count": bucket["usage_count"],
                "category": category_code,
                "category_label": SHOPPING_CATEGORY_LABELS.get(category_code, "Other"),
                "type_options": sorted(bucket["type_options"], key=lambda value: value.lower()),
                "unit_options": _merge_option_values(
                    DEFAULT_SHOPPING_UNIT_OPTIONS,
                    sorted(bucket["unit_options"], key=lambda value: value.lower()),
                ),
                "last_used_unit": bucket["last_used_unit"],
            }
        )

    items.sort(
        key=lambda row: (
            SHOPPING_CATEGORY_ORDER.get(row["category"], 999),
            row["item_name"].lower(),
        )
    )

    category_rows = []
    by_category = {}
    for row in items:
        if row["category"] not in by_category:
            by_category[row["category"]] = {
                "category": row["category"],
                "category_label": row["category_label"],
                "items": [],
            }
        by_category[row["category"]]["items"].append(row)

    for code, _label in SHOPPING_CATEGORY_CHOICES:
        category = by_category.get(code)
        if category and category["items"]:
            category_rows.append(category)
    for code, category in by_category.items():
        if code not in SHOPPING_CATEGORY_LABELS:
            category_rows.append(category)

    return {
        "items": items,
        "categories": category_rows,
    }


@csrf_exempt
def xpenz_mobile_login(request):
    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}

    username = (
        (payload.get("username") if isinstance(payload, dict) else None)
        or request.POST.get("username")
        or (payload.get("email") if isinstance(payload, dict) else None)
        or request.POST.get("email")
        or ""
    ).strip()
    password = (
        (payload.get("password") if isinstance(payload, dict) else None)
        or request.POST.get("password")
        or ""
    )

    if not username or not password:
        return _json_error("Username/email and password are required.", status=400)

    user = authenticate(request, username=username, password=password)
    if not user and "@" in username:
        candidate = User.objects.filter(email__iexact=username).first()
        if candidate:
            user = authenticate(
                request,
                username=candidate.get_username(),
                password=password,
            )

    if not user or not user.is_active:
        return _json_error("Invalid credentials.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    token, _created = XpenzMobileToken.objects.get_or_create(user=user)
    token.last_used_at = timezone.now()
    token.save(update_fields=["last_used_at"])

    return JsonResponse(
        {
            "ok": True,
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.get_username(),
                "name": (user.get_full_name() or user.get_username()).strip(),
            },
        }
    )


@csrf_exempt
def xpenz_estimate_list(request):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    if request.method == "POST":
        payload = {}
        if request.content_type and "application/json" in request.content_type.lower():
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}

        customer_name = (
            (payload.get("customer_name") if isinstance(payload, dict) else None)
            or request.POST.get("customer_name")
            or ""
        ).strip()
        if not customer_name:
            return _json_error("Customer name is required.", status=400)

        requested_caterer_id = (
            (payload.get("caterer_id") if isinstance(payload, dict) else None)
            or request.POST.get("caterer_id")
            or ""
        )
        requested_caterer_id = str(requested_caterer_id).strip()

        if user.is_superuser:
            if requested_caterer_id:
                try:
                    caterer = CatererAccount.objects.get(pk=int(requested_caterer_id))
                except (ValueError, CatererAccount.DoesNotExist):
                    return _json_error("Valid caterer is required.", status=400)
            else:
                caterer = CatererAccount.objects.order_by("name", "id").first()
                if not caterer:
                    return _json_error("Create a company profile first.", status=400)
        else:
            allowed_caterer_ids = sorted(access_map.keys())
            if not allowed_caterer_ids:
                return _json_error("No mobile app access is configured for this user.", status=403)
            if requested_caterer_id:
                try:
                    requested_id_int = int(requested_caterer_id)
                except ValueError:
                    return _json_error("Invalid caterer.", status=400)
                if requested_id_int not in access_map:
                    return _json_error("You do not have access to that company profile.", status=403)
                selected_caterer_id = requested_id_int
            else:
                selected_caterer_id = allowed_caterer_ids[0]
            caterer = get_object_or_404(CatererAccount, pk=selected_caterer_id)

        event_type = (
            (payload.get("event_type") if isinstance(payload, dict) else None)
            or request.POST.get("event_type")
            or "Event"
        ).strip()
        event_location = (
            (payload.get("event_location") if isinstance(payload, dict) else None)
            or request.POST.get("event_location")
            or ""
        ).strip()
        customer_phone = (
            (payload.get("customer_phone") if isinstance(payload, dict) else None)
            or request.POST.get("customer_phone")
            or ""
        ).strip()
        customer_email = (
            (payload.get("customer_email") if isinstance(payload, dict) else None)
            or request.POST.get("customer_email")
            or ""
        ).strip()
        event_date_raw = (
            (payload.get("event_date") if isinstance(payload, dict) else None)
            or request.POST.get("event_date")
            or ""
        ).strip()
        event_date = parse_date(event_date_raw) if event_date_raw else timezone.localdate()
        if event_date_raw and not event_date:
            return _json_error("Event date must be YYYY-MM-DD.", status=400)

        def _safe_int(raw_value, default_value=0):
            try:
                parsed = int(str(raw_value).strip())
            except (TypeError, ValueError):
                return default_value
            return max(parsed, 0)

        guest_count = _safe_int(
            (payload.get("guest_count") if isinstance(payload, dict) else None)
            or request.POST.get("guest_count")
            or 0
        )
        guest_count_kids = _safe_int(
            (payload.get("guest_count_kids") if isinstance(payload, dict) else None)
            or request.POST.get("guest_count_kids")
            or 0
        )

        estimate_type = (
            (payload.get("estimate_type") if isinstance(payload, dict) else None)
            or request.POST.get("estimate_type")
            or "STANDARD"
        ).strip().upper()
        valid_estimate_types = {choice[0] for choice in Estimate._meta.get_field("estimate_type").choices}
        if estimate_type not in valid_estimate_types:
            estimate_type = "STANDARD"

        currency = (
            (payload.get("currency") if isinstance(payload, dict) else None)
            or request.POST.get("currency")
            or caterer.default_currency
        ).strip().upper()
        valid_currencies = {choice[0] for choice in Estimate.CURRENCY_CHOICES}
        if currency not in valid_currencies:
            currency = caterer.default_currency

        counter = caterer.estimate_number_counter or 1000
        estimate = Estimate.objects.create(
            caterer=caterer,
            estimate_number=counter,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            event_type=event_type,
            event_date=event_date,
            event_location=event_location,
            guest_count=guest_count,
            guest_count_kids=guest_count_kids,
            estimate_type=estimate_type,
            currency=currency,
            is_ala_carte=_to_bool(
                (payload.get("is_ala_carte") if isinstance(payload, dict) else None)
                or request.POST.get("is_ala_carte")
                or "0"
            ),
        )
        caterer.estimate_number_counter = counter + 1
        caterer.save(update_fields=["estimate_number_counter"])
        estimate.refresh_from_db()
        estimate.expense_count = 0
        return JsonResponse(
            {"ok": True, "estimate": _serialize_mobile_estimate(request, user, estimate, access_map=access_map)},
            status=201,
        )

    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    estimates = (
        Estimate.objects.select_related("caterer")
        .annotate(
            expense_count=Count("expense_entries"),
            estimate_number_sort=Coalesce("estimate_number", 0),
        )
        .order_by("-estimate_number_sort", "-created_at")
    )
    if not user.is_superuser:
        estimates = estimates.filter(caterer_id__in=list(access_map.keys()))

    results = [
        _serialize_mobile_estimate(request, user, estimate, access_map=access_map)
        for estimate in estimates
    ]

    return JsonResponse({"ok": True, "estimates": results})


def _parse_mobile_meal_plan(raw_value, fallback=None):
    names = []
    if isinstance(raw_value, list):
        names = [_normalize_item_text(part) for part in raw_value]
    elif isinstance(raw_value, str):
        normalized = raw_value.replace(",", "\n")
        names = [_normalize_item_text(part) for part in normalized.splitlines()]
    elif fallback:
        names = [_normalize_item_text(part) for part in fallback]
    cleaned = []
    seen = set()
    for name in names:
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    if not cleaned:
        cleaned = ["Signature Menu"]
    return cleaned


def _remember_material_choices_for_estimate(estimate):
    if not estimate.caterer_id:
        return
    for row in estimate.tablecloth_rows():
        option_name = _normalize_item_text(row.get("name"))
        if not option_name:
            continue
        option, created = TableclothOption.objects.get_or_create(
            caterer_id=estimate.caterer_id,
            name=option_name,
        )
        if not created:
            option.save(update_fields=["last_used_at"])

    plasticware_value = _normalize_item_text(estimate.plasticware_color)
    if plasticware_value:
        option, created = PlasticwareOption.objects.get_or_create(
            caterer_id=estimate.caterer_id,
            name=plasticware_value,
        )
        if not created:
            option.save(update_fields=["last_used_at"])


def _serialize_estimate_builder_payload(request, user, estimate, access_map=None):
    base = _serialize_mobile_estimate(request, user, estimate, access_map=access_map)
    can_view_billing = bool(base.get("can_view_billing"))
    can_edit = _can_edit_estimate_mobile(user, estimate, access_map=access_map)
    estimate.recalc_totals()

    menu_items = list(
        MenuItem.objects.filter(
            caterer_id=estimate.caterer_id,
            is_active=True,
            menu_type=estimate.estimate_type,
        )
        .select_related("category")
        .order_by("category__sort_order", "category__name", "sort_order_override", "name")
    )
    menu_categories_map = {}
    for item in menu_items:
        category_key = item.category_id or 0
        category_name = item.category.name if item.category_id else "Chef's Selection"
        if category_key not in menu_categories_map:
            menu_categories_map[category_key] = {
                "id": item.category_id,
                "name": category_name,
                "items": [],
            }
        menu_categories_map[category_key]["items"].append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description or "",
                "default_servings_per_person": _to_decimal_string(item.default_servings_per_person, "1.00"),
                "cost_per_serving": _to_decimal_string(item.cost_per_serving, "0.00"),
                "markup": _to_decimal_string(item.markup, "0.00"),
                "price_per_serving": _to_decimal_string(item.price_per_serving(), "0.00"),
            }
        )
    # Keep DB/admin order: category sort order first, then item ordering from queryset.
    menu_categories = list(menu_categories_map.values())

    extra_categories_map = {}
    extra_category_labels = {code: label for code, label in ExtraItem.CATEGORY_CHOICES}
    extra_charge_labels = {code: label for code, label in ExtraItem.CHARGE_TYPE_CHOICES}
    extra_items = list(
        ExtraItem.objects.filter(caterer_id=estimate.caterer_id, is_active=True).order_by(
            "category", "name"
        )
    )
    for item in extra_items:
        category_code = item.category or "OTHER"
        if category_code not in extra_categories_map:
            extra_categories_map[category_code] = {
                "code": category_code,
                "label": extra_category_labels.get(category_code, category_code.title()),
                "items": [],
            }
        extra_categories_map[category_code]["items"].append(
            {
                "id": item.id,
                "name": item.name,
                "category": category_code,
                "category_label": extra_category_labels.get(category_code, category_code.title()),
                "charge_type": item.charge_type,
                "charge_type_label": extra_charge_labels.get(item.charge_type, item.charge_type),
                "price": _to_decimal_string(item.price, "0.00"),
                "cost": _to_decimal_string(item.cost, "0.00"),
                "notes": item.notes or "",
            }
        )
    extra_categories = sorted(
        extra_categories_map.values(),
        key=lambda row: row["label"].lower(),
    )

    meal_plan = estimate.get_meal_plan()
    default_meal_name = meal_plan[0] if meal_plan else estimate.default_meal_name()
    menu_choices = []
    for row in estimate.food_choices.select_related("menu_item").order_by(
        "meal_name",
        "menu_item__name",
    ):
        if not row.menu_item_id:
            continue
        menu_choices.append(
            {
                "menu_item_id": row.menu_item_id,
                "meal_name": row.meal_name or default_meal_name,
                "servings_per_person": _to_decimal_string(
                    row.servings_per_person or row.menu_item.default_servings_per_person,
                    "1.00",
                ),
                "notes": row.notes or "",
                "included": bool(row.included),
            }
        )

    extra_lines = []
    for row in estimate.extra_lines.select_related("extra_item").order_by("extra_item__name"):
        if not row.extra_item_id:
            continue
        extra_lines.append(
            {
                "extra_item_id": row.extra_item_id,
                "quantity": _to_decimal_string(row.quantity, "1.00"),
                "override_price": _to_decimal_string(row.override_price),
                "notes": row.notes or "",
                "included": True,
            }
        )

    summary = {
        "waiter_count": int(estimate.total_waiter_count() or 0),
        "food_total": _to_decimal_string(estimate.meal_grand_total(), "0.00") if can_view_billing else "",
        "food_price_per_person": _to_decimal_string(estimate.food_price_per_person, "0.00")
        if can_view_billing
        else "",
        "extras_total": _to_decimal_string(estimate.extras_total, "0.00") if can_view_billing else "",
        "staff_total": _to_decimal_string(estimate.staff_total, "0.00") if can_view_billing else "",
        "dishes_total": _to_decimal_string(estimate.dishes_total, "0.00") if can_view_billing else "",
        "grand_total": _to_decimal_string(estimate.grand_total, "0.00") if can_view_billing else "",
        "deposit_amount": _to_decimal_string(estimate.deposit_amount, "0.00") if can_view_billing else "",
        "balance_due": _to_decimal_string(estimate.balance_due, "0.00") if can_view_billing else "",
    }

    meal_sections = []
    for section in estimate.meal_sections():
        meal_sections.append(
            {
                "name": section.get("name", ""),
                "price_per_guest": (
                    _to_decimal_string(section.get("price_per_guest"), "0.00")
                    if can_view_billing
                    else ""
                ),
                "price_per_child": (
                    _to_decimal_string(section.get("price_per_child"), "0.00")
                    if can_view_billing
                    else ""
                ),
                "total": (
                    _to_decimal_string(section.get("total"), "0.00")
                    if can_view_billing
                    else ""
                ),
                "kids_total": (
                    _to_decimal_string(section.get("kids_total"), "0.00")
                    if can_view_billing
                    else ""
                ),
                "guest_count": _to_decimal_string(section.get("guest_count"), "0"),
                "guest_count_kids": _to_decimal_string(section.get("guest_count_kids"), "0"),
            }
        )

    manual_meal_totals = {}
    for raw_meal, raw_value in (estimate.manual_meal_totals or {}).items():
        meal_name = _normalize_item_text(raw_meal)
        if not meal_name:
            continue
        parsed_value = Estimate._clean_decimal(raw_value, None)
        if parsed_value is None:
            continue
        manual_meal_totals[meal_name] = _to_decimal_string(
            parsed_value.quantize(Decimal("0.01")),
            "0.00",
        )

    meal_guest_overrides = {}
    for raw_meal, raw_override in (estimate.meal_guest_overrides or {}).items():
        meal_name = _normalize_item_text(raw_meal)
        if not meal_name or not isinstance(raw_override, dict):
            continue
        normalized_row = {}
        for key in ("adults", "kids"):
            parsed_value = Estimate._clean_decimal(raw_override.get(key), None)
            if parsed_value is None:
                continue
            if parsed_value == parsed_value.to_integral_value():
                normalized_row[key] = int(parsed_value)
            else:
                normalized_row[key] = float(parsed_value)
        if normalized_row:
            meal_guest_overrides[meal_name] = normalized_row

    meal_service_details = {}
    for raw_meal, raw_row in (estimate.meal_service_details or {}).items():
        meal_name = _normalize_item_text(raw_meal)
        if not meal_name or not isinstance(raw_row, dict):
            continue
        normalized_row = {}
        if _to_bool(raw_row.get("wants_real_dishes")):
            normalized_row["wants_real_dishes"] = True
        for key in (
            "real_dishes_price_per_person",
            "staff_hours",
            "staff_tip_per_waiter",
        ):
            parsed_value = Estimate._clean_decimal(raw_row.get(key), None)
            if parsed_value is None:
                continue
            normalized_row[key] = _to_decimal_string(
                parsed_value.quantize(Decimal("0.01")),
                "0.00",
            )
        parsed_waiters = Estimate._clean_int(raw_row.get("wait_staff_count"), None)
        if parsed_waiters is not None:
            normalized_row["wait_staff_count"] = int(parsed_waiters)
        if normalized_row:
            meal_service_details[meal_name] = normalized_row

    return {
        "ok": True,
        "estimate_id": estimate.id,
        "estimate": {
            **base,
            "can_edit": can_edit,
            "customer_phone": estimate.customer_phone or "",
            "customer_email": estimate.customer_email or "",
            "event_date": estimate.event_date.isoformat() if estimate.event_date else "",
            "is_ala_carte": bool(estimate.is_ala_carte),
            "include_premium_plastic": bool(estimate.include_premium_plastic),
            "include_premium_tablecloths": bool(estimate.include_premium_tablecloths),
            "plasticware_color": estimate.plasticware_color or "",
            "wants_real_dishes": bool(estimate.wants_real_dishes),
            "real_dishes_price_per_person": _to_decimal_string(estimate.real_dishes_price_per_person),
            "real_dishes_flat_fee": _to_decimal_string(estimate.real_dishes_flat_fee),
            "staff_hours": _to_decimal_string(estimate.staff_hours, "0.00"),
            "extra_waiters": int(estimate.extra_waiters or 0),
            "staff_count_override": (
                int(estimate.staff_count_override) if estimate.staff_count_override is not None else None
            ),
            "staff_hourly_rate": _to_decimal_string(estimate.staff_hourly_rate),
            "staff_tip_per_waiter": _to_decimal_string(estimate.staff_tip_per_waiter),
            "client_tipped_at_event": bool(estimate.client_tipped_at_event),
            "notes_internal": estimate.notes_internal or "",
            "notes_for_customer": estimate.notes_for_customer or "",
            "payment_terms": estimate.payment_terms or "",
            "payment_method": estimate.payment_method or "",
            "payment_instructions": estimate.payment_instructions or "",
            "contract_terms": estimate.contract_terms or "",
            "terms_acknowledged": bool(estimate.terms_acknowledged),
            "signature_name": estimate.signature_name or "",
            "signature_title": estimate.signature_title or "",
            "signature_date": estimate.signature_date.isoformat() if estimate.signature_date else "",
            "deposit_percentage": _to_decimal_string(estimate.deposit_percentage, "0.00"),
            "deposit_received": _to_decimal_string(estimate.deposit_received, "0.00"),
            "kids_discount_percentage": _to_decimal_string(estimate.kids_discount_percentage, "0.00"),
            "exchange_rate": _to_decimal_string(estimate.exchange_rate, "1.0000"),
            "meal_plan": meal_plan,
            "manual_meal_totals": manual_meal_totals,
            "meal_guest_overrides": meal_guest_overrides,
            "meal_service_details": meal_service_details,
            "meal_sections": meal_sections,
            "tablecloth_details": estimate.tablecloth_details or {},
            "summary": summary,
        },
        "catalog": {
            "currencies": [
                {"code": code, "label": label} for code, label in Estimate.CURRENCY_CHOICES
            ],
            "payment_methods": [
                {"code": code, "label": label} for code, label in PAYMENT_METHOD_CHOICES
            ],
            "meal_plan": meal_plan,
            "menu_categories": menu_categories,
            "extra_categories": extra_categories,
            "tablecloth_options": list(
                TableclothOption.objects.filter(caterer_id=estimate.caterer_id)
                .order_by("name")
                .values_list("name", flat=True)
            ),
            "plasticware_options": list(
                PlasticwareOption.objects.filter(caterer_id=estimate.caterer_id)
                .order_by("name")
                .values_list("name", flat=True)
            ),
        },
        "selections": {
            "menu_choices": menu_choices,
            "extra_lines": extra_lines,
        },
    }


@csrf_exempt
def xpenz_estimate_builder(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)

    if request.method == "GET":
        return JsonResponse(
            _serialize_estimate_builder_payload(request, user, estimate, access_map=access_map)
        )

    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    if not _can_edit_estimate_mobile(user, estimate, access_map=access_map):
        return _json_error("You do not have permission to edit this estimate.", status=403)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    estimate_payload = payload.get("estimate")
    if not isinstance(estimate_payload, dict):
        estimate_payload = payload
    if not isinstance(estimate_payload, dict):
        estimate_payload = {}

    def _parse_positive_int(value, allow_none=False):
        if value in (None, ""):
            return None if allow_none else 0
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if parsed < 0:
            return None
        return parsed

    def _parse_decimal(value, allow_none=False, quantize_str="0.01"):
        if value in (None, ""):
            return None if allow_none else Decimal("0.00")
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError):
            return None
        if parsed < Decimal("0.00"):
            return None
        if quantize_str:
            parsed = parsed.quantize(Decimal(quantize_str))
        return parsed

    if "customer_name" in estimate_payload:
        customer_name = _normalize_item_text(estimate_payload.get("customer_name"))
        if not customer_name:
            return _json_error("Customer name is required.", status=400)
        estimate.customer_name = customer_name
    if "customer_phone" in estimate_payload:
        estimate.customer_phone = _normalize_item_text(estimate_payload.get("customer_phone"))
    if "customer_email" in estimate_payload:
        estimate.customer_email = _normalize_item_text(estimate_payload.get("customer_email"))
    if "event_type" in estimate_payload:
        estimate.event_type = _normalize_item_text(estimate_payload.get("event_type"))
    if "event_location" in estimate_payload:
        estimate.event_location = _normalize_item_text(estimate_payload.get("event_location"))
    if "event_date" in estimate_payload:
        raw_event_date = _normalize_item_text(estimate_payload.get("event_date"))
        if raw_event_date:
            event_date = parse_date(raw_event_date)
            if not event_date:
                return _json_error("Event date must be YYYY-MM-DD.", status=400)
            estimate.event_date = event_date
    if "signature_date" in estimate_payload:
        raw_signature_date = _normalize_item_text(estimate_payload.get("signature_date"))
        if raw_signature_date:
            signature_date = parse_date(raw_signature_date)
            if not signature_date:
                return _json_error("Signature date must be YYYY-MM-DD.", status=400)
            estimate.signature_date = signature_date
        else:
            estimate.signature_date = None
    if "guest_count" in estimate_payload:
        guest_count = _parse_positive_int(estimate_payload.get("guest_count"))
        if guest_count is None:
            return _json_error("Guest count must be a non-negative integer.", status=400)
        estimate.guest_count = guest_count
    if "guest_count_kids" in estimate_payload:
        guest_count_kids = _parse_positive_int(estimate_payload.get("guest_count_kids"))
        if guest_count_kids is None:
            return _json_error("Kids guest count must be a non-negative integer.", status=400)
        estimate.guest_count_kids = guest_count_kids
    if "extra_waiters" in estimate_payload:
        extra_waiters = _parse_positive_int(estimate_payload.get("extra_waiters"))
        if extra_waiters is None:
            return _json_error("Extra waiters must be a non-negative integer.", status=400)
        estimate.extra_waiters = extra_waiters
    if "staff_count_override" in estimate_payload:
        staff_count_override = _parse_positive_int(
            estimate_payload.get("staff_count_override"),
            allow_none=True,
        )
        if estimate_payload.get("staff_count_override") not in (None, "") and staff_count_override is None:
            return _json_error("Staff count override must be a non-negative integer.", status=400)
        estimate.staff_count_override = staff_count_override
    if "currency" in estimate_payload:
        currency = _normalize_item_text(estimate_payload.get("currency")).upper()
        valid_currencies = {code for code, _label in Estimate.CURRENCY_CHOICES}
        if currency and currency not in valid_currencies:
            return _json_error("Invalid currency code.", status=400)
        if currency:
            estimate.currency = currency
    if "payment_method" in estimate_payload:
        payment_method = _normalize_item_text(estimate_payload.get("payment_method")).upper()
        valid_payment_methods = {code for code, _label in PAYMENT_METHOD_CHOICES}
        if payment_method and payment_method not in valid_payment_methods:
            return _json_error("Invalid payment method.", status=400)
        estimate.payment_method = payment_method
    if "staff_hours" in estimate_payload:
        staff_hours = _parse_decimal(estimate_payload.get("staff_hours"))
        if staff_hours is None:
            return _json_error("Staff hours must be a non-negative number.", status=400)
        estimate.staff_hours = staff_hours
    if "kids_discount_percentage" in estimate_payload:
        kids_discount_percentage = _parse_decimal(estimate_payload.get("kids_discount_percentage"))
        if kids_discount_percentage is None:
            return _json_error("Kids discount percentage must be a non-negative number.", status=400)
        estimate.kids_discount_percentage = kids_discount_percentage
    if "exchange_rate" in estimate_payload:
        exchange_rate = _parse_decimal(
            estimate_payload.get("exchange_rate"),
            quantize_str="0.0001",
        )
        if exchange_rate is None or exchange_rate <= Decimal("0.00"):
            return _json_error("Exchange rate must be a positive number.", status=400)
        estimate.exchange_rate = exchange_rate
    if "real_dishes_price_per_person" in estimate_payload:
        estimate.real_dishes_price_per_person = _parse_decimal(
            estimate_payload.get("real_dishes_price_per_person"),
            allow_none=True,
        )
    if "real_dishes_flat_fee" in estimate_payload:
        estimate.real_dishes_flat_fee = _parse_decimal(
            estimate_payload.get("real_dishes_flat_fee"),
            allow_none=True,
        )
    if "staff_hourly_rate" in estimate_payload:
        estimate.staff_hourly_rate = _parse_decimal(
            estimate_payload.get("staff_hourly_rate"),
            allow_none=True,
        )
    if "staff_tip_per_waiter" in estimate_payload:
        estimate.staff_tip_per_waiter = _parse_decimal(
            estimate_payload.get("staff_tip_per_waiter"),
            allow_none=True,
        )
    if "deposit_percentage" in estimate_payload:
        deposit_percentage = _parse_decimal(estimate_payload.get("deposit_percentage"))
        if deposit_percentage is None:
            return _json_error("Deposit percentage must be a non-negative number.", status=400)
        estimate.deposit_percentage = deposit_percentage
    if "deposit_received" in estimate_payload:
        deposit_received = _parse_decimal(estimate_payload.get("deposit_received"))
        if deposit_received is None:
            return _json_error("Deposit received must be a non-negative number.", status=400)
        estimate.deposit_received = deposit_received

    if "is_ala_carte" in estimate_payload:
        estimate.is_ala_carte = _to_bool(estimate_payload.get("is_ala_carte"))
    if "include_premium_plastic" in estimate_payload:
        estimate.include_premium_plastic = _to_bool(
            estimate_payload.get("include_premium_plastic")
        )
    if "include_premium_tablecloths" in estimate_payload:
        estimate.include_premium_tablecloths = _to_bool(
            estimate_payload.get("include_premium_tablecloths")
        )
    if "wants_real_dishes" in estimate_payload:
        estimate.wants_real_dishes = _to_bool(estimate_payload.get("wants_real_dishes"))
    if "client_tipped_at_event" in estimate_payload:
        estimate.client_tipped_at_event = _to_bool(
            estimate_payload.get("client_tipped_at_event")
        )
    if "terms_acknowledged" in estimate_payload:
        estimate.terms_acknowledged = _to_bool(estimate_payload.get("terms_acknowledged"))

    if "plasticware_color" in estimate_payload:
        estimate.plasticware_color = _normalize_item_text(estimate_payload.get("plasticware_color"))
    if "notes_internal" in estimate_payload:
        estimate.notes_internal = (estimate_payload.get("notes_internal") or "").strip()
    if "notes_for_customer" in estimate_payload:
        estimate.notes_for_customer = (estimate_payload.get("notes_for_customer") or "").strip()
    if "payment_terms" in estimate_payload:
        estimate.payment_terms = (estimate_payload.get("payment_terms") or "").strip()
    if "payment_instructions" in estimate_payload:
        estimate.payment_instructions = (estimate_payload.get("payment_instructions") or "").strip()
    if "contract_terms" in estimate_payload:
        estimate.contract_terms = (estimate_payload.get("contract_terms") or "").strip()
    if "signature_name" in estimate_payload:
        estimate.signature_name = _normalize_item_text(estimate_payload.get("signature_name"))
    if "signature_title" in estimate_payload:
        estimate.signature_title = _normalize_item_text(estimate_payload.get("signature_title"))

    meal_plan_payload = payload.get("meal_plan")
    meal_plan = estimate.get_meal_plan()
    if meal_plan_payload is not None:
        meal_plan = _parse_mobile_meal_plan(meal_plan_payload, fallback=meal_plan)
        estimate.meal_plan = meal_plan

    if "tablecloth_details" in estimate_payload:
        raw_tablecloths = estimate_payload.get("tablecloth_details")
        if isinstance(raw_tablecloths, str):
            try:
                raw_tablecloths = json.loads(raw_tablecloths) if raw_tablecloths else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_tablecloths = {}
        if not isinstance(raw_tablecloths, dict):
            raw_tablecloths = {}
        ordered_meals = list(meal_plan)
        for key in raw_tablecloths.keys():
            if key not in ordered_meals:
                ordered_meals.append(key)
        parsed_tablecloths = {}
        for meal_name in ordered_meals:
            row = raw_tablecloths.get(meal_name) or {}
            if not isinstance(row, dict):
                continue
            name = _normalize_item_text(row.get("name") or row.get("choice"))
            quantity = Estimate._clean_decimal(row.get("quantity"), Decimal("0.00")) or Decimal("0.00")
            extra_charge = Estimate._clean_decimal(row.get("extra_charge"), None)
            has_price = extra_charge not in (None, Decimal("0.00"))
            if not name and quantity in (None, Decimal("0.00")) and not has_price:
                continue
            parsed_tablecloths[meal_name] = {
                "name": name,
                "quantity": str(quantity.quantize(Decimal("0.01"))),
                "extra_charge": (
                    str(extra_charge.quantize(Decimal("0.01"))) if has_price else None
                ),
            }
        estimate.tablecloth_details = parsed_tablecloths

    if "manual_meal_totals" in estimate_payload:
        raw_manual_totals = estimate_payload.get("manual_meal_totals")
        if isinstance(raw_manual_totals, str):
            try:
                raw_manual_totals = json.loads(raw_manual_totals) if raw_manual_totals else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_manual_totals = {}
        if not isinstance(raw_manual_totals, dict):
            return _json_error("Manual meal totals must be a JSON object.", status=400)
        parsed_manual_totals = {}
        for raw_meal_name, raw_value in raw_manual_totals.items():
            meal_name = _normalize_item_text(raw_meal_name)
            if not meal_name:
                continue
            value_text = str(raw_value).strip() if raw_value is not None else ""
            if not value_text:
                continue
            parsed_value = _parse_decimal(value_text, allow_none=True)
            if parsed_value is None:
                return _json_error(
                    f'Meal override for "{meal_name}" must be a non-negative number.',
                    status=400,
                )
            parsed_manual_totals[meal_name] = str(parsed_value)
        estimate.manual_meal_totals = parsed_manual_totals

    if "meal_guest_overrides" in estimate_payload:
        raw_guest_overrides = estimate_payload.get("meal_guest_overrides")
        if isinstance(raw_guest_overrides, str):
            try:
                raw_guest_overrides = (
                    json.loads(raw_guest_overrides) if raw_guest_overrides else {}
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_guest_overrides = {}
        if not isinstance(raw_guest_overrides, dict):
            return _json_error("Meal guest overrides must be a JSON object.", status=400)
        parsed_guest_overrides = {}
        for raw_meal_name, raw_row in raw_guest_overrides.items():
            meal_name = _normalize_item_text(raw_meal_name)
            if not meal_name:
                continue
            if not isinstance(raw_row, dict):
                continue
            parsed_row = {}
            for key in ("adults", "kids"):
                value_text = str(raw_row.get(key)).strip() if raw_row.get(key) is not None else ""
                if not value_text:
                    continue
                parsed_value = _parse_positive_int(value_text, allow_none=True)
                if parsed_value is None:
                    label = "Adults" if key == "adults" else "Kids"
                    return _json_error(
                        f'{label} override for "{meal_name}" must be a non-negative integer.',
                        status=400,
                    )
                parsed_row[key] = parsed_value
            if parsed_row:
                parsed_guest_overrides[meal_name] = parsed_row
        estimate.meal_guest_overrides = parsed_guest_overrides

    if "meal_service_details" in estimate_payload:
        raw_service_details = estimate_payload.get("meal_service_details")
        if isinstance(raw_service_details, str):
            try:
                raw_service_details = (
                    json.loads(raw_service_details) if raw_service_details else {}
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_service_details = {}
        if not isinstance(raw_service_details, dict):
            return _json_error("Per-meal logistics must be a JSON object.", status=400)

        ordered_meals = list(meal_plan)
        raw_service_by_meal = {}
        for key in raw_service_details.keys():
            meal_name = _normalize_item_text(key)
            if meal_name and meal_name not in ordered_meals:
                ordered_meals.append(meal_name)
            row = raw_service_details.get(key)
            if meal_name and isinstance(row, dict):
                raw_service_by_meal[meal_name] = row

        parsed_service_details = {}
        decimal_field_labels = {
            "real_dishes_price_per_person": "Real dishes price per guest",
            "staff_hours": "Staff hours",
            "staff_tip_per_waiter": "Tip per waiter",
        }
        for meal_name in ordered_meals:
            raw_row = raw_service_by_meal.get(meal_name)
            if not isinstance(raw_row, dict):
                continue
            parsed_row = {}
            if _to_bool(raw_row.get("wants_real_dishes")):
                parsed_row["wants_real_dishes"] = True

            for key, label in decimal_field_labels.items():
                raw_value = raw_row.get(key)
                value_text = str(raw_value).strip() if raw_value is not None else ""
                if not value_text:
                    continue
                parsed_value = _parse_decimal(value_text, allow_none=True)
                if parsed_value is None:
                    return _json_error(
                        f'{label} for "{meal_name}" must be a non-negative number.',
                        status=400,
                    )
                parsed_row[key] = str(parsed_value)

            raw_waiters = raw_row.get("wait_staff_count")
            waiters_text = str(raw_waiters).strip() if raw_waiters is not None else ""
            if waiters_text:
                parsed_waiters = _parse_positive_int(waiters_text, allow_none=True)
                if parsed_waiters is None:
                    return _json_error(
                        f'Wait staff qty for "{meal_name}" must be a non-negative integer.',
                        status=400,
                    )
                parsed_row["wait_staff_count"] = parsed_waiters

            if parsed_row:
                parsed_service_details[meal_name] = parsed_row

        estimate.meal_service_details = parsed_service_details

    estimate.save()

    menu_choices_payload = payload.get("menu_choices")
    if isinstance(menu_choices_payload, list):
        menu_item_map = {
            row.id: row
            for row in MenuItem.objects.filter(
                caterer_id=estimate.caterer_id,
                is_active=True,
                menu_type=estimate.estimate_type,
            )
        }
        selected_rows = []
        seen = set()
        default_meal_name = meal_plan[0] if meal_plan else estimate.default_meal_name()
        for raw_row in menu_choices_payload:
            if not isinstance(raw_row, dict):
                continue
            raw_menu_item_id = raw_row.get("menu_item_id")
            if not str(raw_menu_item_id or "").isdigit():
                continue
            menu_item = menu_item_map.get(int(raw_menu_item_id))
            if not menu_item:
                continue
            included = _to_bool(raw_row.get("included", True))
            if not included:
                continue
            meal_name = _normalize_item_text(raw_row.get("meal_name")) or default_meal_name
            if meal_name and meal_name not in meal_plan:
                meal_plan.append(meal_name)
            servings = Estimate._clean_decimal(
                raw_row.get("servings_per_person"),
                menu_item.default_servings_per_person,
            )
            if servings is None or servings <= Decimal("0.00"):
                servings = menu_item.default_servings_per_person
            notes = (raw_row.get("notes") or "").strip()[:255]
            key = (menu_item.id, meal_name.lower())
            if key in seen:
                continue
            seen.add(key)
            selected_rows.append(
                EstimateFoodChoice(
                    estimate=estimate,
                    menu_item=menu_item,
                    meal_name=meal_name,
                    included=True,
                    servings_per_person=servings,
                    notes=notes,
                )
            )
        EstimateFoodChoice.objects.filter(estimate=estimate).delete()
        if selected_rows:
            EstimateFoodChoice.objects.bulk_create(selected_rows)
        estimate.meal_plan = meal_plan

    extra_lines_payload = payload.get("extra_lines")
    if isinstance(extra_lines_payload, list):
        extra_item_map = {
            row.id: row
            for row in ExtraItem.objects.filter(
                caterer_id=estimate.caterer_id,
                is_active=True,
            )
        }
        selected_rows = []
        seen_extra_ids = set()
        for raw_row in extra_lines_payload:
            if not isinstance(raw_row, dict):
                continue
            raw_extra_item_id = raw_row.get("extra_item_id")
            if not str(raw_extra_item_id or "").isdigit():
                continue
            extra_item = extra_item_map.get(int(raw_extra_item_id))
            if not extra_item:
                continue
            included = _to_bool(raw_row.get("included", True))
            if not included:
                continue
            if extra_item.id in seen_extra_ids:
                continue
            seen_extra_ids.add(extra_item.id)
            quantity = Estimate._clean_decimal(raw_row.get("quantity"), Decimal("1.00"))
            if quantity is None or quantity <= Decimal("0.00"):
                quantity = Decimal("1.00")
            override_price = Estimate._clean_decimal(raw_row.get("override_price"), None)
            notes = (raw_row.get("notes") or "").strip()[:255]
            selected_rows.append(
                EstimateExtraItem(
                    estimate=estimate,
                    extra_item=extra_item,
                    quantity=quantity,
                    override_price=override_price,
                    notes=notes,
                )
            )
        EstimateExtraItem.objects.filter(estimate=estimate).delete()
        if selected_rows:
            EstimateExtraItem.objects.bulk_create(selected_rows)

    _remember_material_choices_for_estimate(estimate)
    estimate.save()
    estimate.refresh_from_db()
    estimate.expense_count = estimate.expense_entries.count()
    return JsonResponse(
        _serialize_estimate_builder_payload(request, user, estimate, access_map=access_map)
    )


@csrf_exempt
def xpenz_estimate_print_html(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)

    variant = (request.GET.get("variant") or "estimate").strip().lower()
    if variant not in {"estimate", "flat", "planner", "workflow"}:
        return _json_error("Invalid print variant.", status=400)

    # Delegate to admin print rendering so page-breaks, compacting, and styling
    # stay identical to the admin panel output.
    from .admin import EstimateAdmin

    effective_user = user
    if not user.is_superuser and estimate.caterer.owner_id != user.id:
        access = _mobile_access_for_caterer(
            user, estimate.caterer_id, access_map=access_map
        ) or {}
        can_view_billing = bool(access.get("can_view_job_billing"))
        if variant in {"estimate", "flat"} and not can_view_billing:
            return _json_error(
                "You do not have permission to view billing printouts.",
                status=403,
            )
        effective_user = estimate.caterer.owner

    request.user = effective_user
    admin_view = EstimateAdmin(Estimate, django_admin.site)

    try:
        if variant == "planner":
            response = admin_view.print_planner(request, estimate_id)
            return _clamp_mobile_print_html(response)
        if variant == "flat":
            response = admin_view.print_estimate_flat(request, estimate_id)
            return _clamp_mobile_print_html(response)
        if variant == "workflow":
            response = admin_view.workflow_view(request, estimate_id)
            return _clamp_mobile_print_html(response)
        response = admin_view.print_estimate(request, estimate_id)
        return _clamp_mobile_print_html(response)
    except PermissionDenied:
        return _json_error("You do not have access to this printout.", status=403)
    except Exception as exc:
        logger.exception(
            "xpenz_estimate_print_html failed",
            extra={"estimate_id": estimate_id, "variant": variant},
        )
        return _json_error(f"Print rendering failed: {exc}", status=500)


@csrf_exempt
def xpenz_estimate_expenses(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)

    if request.method == "GET":
        entries = list(
            estimate.expense_entries.select_related("created_by").order_by("-created_at")
        )
        return JsonResponse(
            {
                "ok": True,
                "estimate_id": estimate.id,
                "entries": [_serialize_expense_entry(request, entry) for entry in entries],
            }
        )

    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)
    if not _can_add_expenses(user, estimate, access_map=access_map):
        return _json_error("You do not have permission to add expenses.", status=403)

    receipt_image = request.FILES.get("receipt_image")
    voice_note = request.FILES.get("voice_note")
    is_manual_only = _to_bool(
        request.POST.get("is_manual_only") or request.POST.get("manual_only") or "0"
    )

    if not is_manual_only:
        if not receipt_image:
            return _json_error("`receipt_image` file is required.", status=400)

    raw_duration = (
        request.POST.get("voice_note_duration_seconds")
        or request.POST.get("voice_duration_seconds")
        or ""
    ).strip()
    duration_seconds = None
    if raw_duration:
        try:
            parsed_duration = int(float(raw_duration))
            if parsed_duration >= 0:
                duration_seconds = parsed_duration
        except (TypeError, ValueError):
            duration_seconds = None

    raw_amount = (request.POST.get("expense_amount") or "").strip()
    expense_amount = None
    if raw_amount:
        try:
            amount = Decimal(raw_amount)
            if amount >= Decimal("0.00"):
                expense_amount = amount.quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            expense_amount = None

    expense_text = (request.POST.get("expense_text") or "").strip()
    note_text = (request.POST.get("note_text") or "").strip()
    if is_manual_only and not expense_text and expense_amount is None and not note_text:
        return _json_error(
            "Manual entries require at least expense text, amount, or note text.",
            status=400,
        )

    entry = EstimateExpenseEntry.objects.create(
        estimate=estimate,
        created_by=user,
        receipt_image=receipt_image,
        voice_note=voice_note,
        note_text=note_text,
        expense_text=expense_text,
        expense_amount=expense_amount,
        is_manual_only=is_manual_only,
        voice_note_duration_seconds=duration_seconds,
    )

    return JsonResponse(
        {
            "ok": True,
            "estimate_id": estimate.id,
            "entry": _serialize_expense_entry(request, entry),
        },
        status=201,
    )


@csrf_exempt
def xpenz_staff_summary(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)
    if not _can_manage_staff(user, estimate, access_map=access_map):
        return _json_error("You do not have permission to manage staff.", status=403)

    entries = list(
        estimate.staff_time_entries.select_related("expense_entry").order_by("-punched_in_at")
    )
    total_staff_cost = sum(
        (entry.total_cost or Decimal("0.00") for entry in entries),
        Decimal("0.00"),
    )
    unapplied_staff_cost = sum(
        (
            entry.total_cost or Decimal("0.00")
            for entry in entries
            if entry.punched_out_at and not entry.applied_to_expenses
        ),
        Decimal("0.00"),
    )

    return JsonResponse(
        {
            "ok": True,
            "estimate_id": estimate.id,
            "roles": _staff_role_rows_for_estimate(request, estimate),
            "entries": [_serialize_staff_entry(entry) for entry in entries],
            "total_staff_cost": str(total_staff_cost.quantize(Decimal("0.01"))),
            "unapplied_staff_cost": str(unapplied_staff_cost.quantize(Decimal("0.01"))),
        }
    )


@csrf_exempt
def xpenz_apply_staff_costs_to_expense(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)
    if not _can_manage_staff(user, estimate, access_map=access_map):
        return _json_error("You do not have permission to manage staff.", status=403)
    if not _can_add_expenses(user, estimate, access_map=access_map):
        return _json_error("You do not have permission to add expenses.", status=403)

    pending_entries = list(
        estimate.staff_time_entries.filter(
            punched_out_at__isnull=False,
            applied_to_expenses=False,
        ).order_by("punched_in_at")
    )
    if not pending_entries:
        return _json_error("No unapplied staff costs found for this estimate.", status=400)

    total = sum(
        (entry.total_cost or Decimal("0.00") for entry in pending_entries),
        Decimal("0.00"),
    )
    total = total.quantize(Decimal("0.01"))
    if total <= Decimal("0.00"):
        return _json_error("Staff cost total is zero.", status=400)

    role_counts = {}
    for entry in pending_entries:
        role_counts[entry.role] = role_counts.get(entry.role, 0) + 1
    role_bits = []
    role_labels = dict(STAFF_ROLE_CHOICES)
    for role_code, count in role_counts.items():
        role_bits.append(f"{role_labels.get(role_code, role_code)} x{count}")

    expense_entry = EstimateExpenseEntry.objects.create(
        estimate=estimate,
        created_by=user,
        is_manual_only=True,
        expense_text="Staff payroll cost",
        expense_amount=total,
        note_text="Auto-added from staff punch records. " + ", ".join(role_bits),
    )

    EstimateStaffTimeEntry.objects.filter(id__in=[entry.id for entry in pending_entries]).update(
        applied_to_expenses=True,
        expense_entry=expense_entry,
    )

    return JsonResponse(
        {
            "ok": True,
            "estimate_id": estimate.id,
            "expense_entry_id": expense_entry.id,
            "applied_total": str(total),
            "entry_count": len(pending_entries),
        }
    )


@csrf_exempt
def xpenz_shopping_lists(request):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    if request.method == "GET":
        rows = ShoppingList.objects.select_related(
            "caterer",
            "estimate",
            "created_by",
            "execution_started_by",
        ).filter(
            deleted_at__isnull=True,
        ).annotate(
            item_count=Count("items", filter=Q(items__is_completed=False))
        )
        if not user.is_superuser:
            rows = rows.filter(caterer_id__in=list(access_map.keys()))
        rows = rows.order_by("-updated_at", "-created_at")
        return JsonResponse(
            {
                "ok": True,
                "lists": [_serialize_shopping_list_entry(row) for row in rows],
            }
        )

    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    raw_title = (
        payload.get("title")
        if payload.get("title") is not None
        else request.POST.get("title")
    )
    title = _normalize_item_text(raw_title or "")

    raw_estimate_id = payload.get("estimate_id")
    if raw_estimate_id is None:
        raw_estimate_id = request.POST.get("estimate_id")
    raw_caterer_id = payload.get("caterer_id")
    if raw_caterer_id is None:
        raw_caterer_id = request.POST.get("caterer_id")

    estimate = None
    caterer = None

    if str(raw_estimate_id or "").strip():
        if not str(raw_estimate_id).isdigit():
            return _json_error("Invalid estimate id.", status=400)
        estimate = get_object_or_404(
            Estimate.objects.select_related("caterer"),
            pk=int(raw_estimate_id),
        )
        access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
        if not access:
            return _json_error("You do not have access to this estimate.", status=403)
        caterer = estimate.caterer

    if caterer is None:
        if str(raw_caterer_id or "").strip():
            if not str(raw_caterer_id).isdigit():
                return _json_error("Invalid caterer id.", status=400)
            caterer_id = int(raw_caterer_id)
            access = _mobile_access_for_caterer(user, caterer_id, access_map=access_map)
            if not access:
                return _json_error("You do not have access to this caterer.", status=403)
            caterer = get_object_or_404(CatererAccount, pk=caterer_id)
        else:
            if user.is_superuser:
                return _json_error("`caterer_id` is required for superusers.", status=400)
            available_ids = list(access_map.keys())
            if len(available_ids) == 1:
                caterer = get_object_or_404(CatererAccount, pk=available_ids[0])
            elif not available_ids:
                return _json_error("No caterer access found for this user.", status=403)
            else:
                return _json_error("`caterer_id` is required when multiple caterers are available.", status=400)

    if not title:
        if estimate:
            title = f"{estimate.customer_name} Shopping"
        else:
            title = f"{caterer.name} Shopping"

    created = ShoppingList.objects.create(
        caterer=caterer,
        estimate=estimate,
        title=title,
        created_by=user,
    )
    return JsonResponse(
        {
            "ok": True,
            "shopping_list": _serialize_shopping_list_entry(created),
        },
        status=201,
    )


def _shopping_list_for_user(user, shopping_list_id, access_map):
    entry = get_object_or_404(
        ShoppingList.objects.select_related(
            "caterer",
            "estimate",
            "created_by",
            "execution_started_by",
        ),
        pk=shopping_list_id,
    )
    access = _mobile_access_for_caterer(user, entry.caterer_id, access_map=access_map)
    if not access and not user.is_superuser:
        raise PermissionDenied("You do not have access to this shopping list.")
    return entry


def _active_shopping_items_sorted(shopping_list):
    item_rows = list(shopping_list.items.filter(is_completed=False))
    return sorted(
        item_rows,
        key=lambda row: (
            SHOPPING_CATEGORY_ORDER.get(row.category, 999),
            (row.item_name or "").lower(),
            (row.item_type or "").lower(),
            (row.item_unit or "").lower(),
            row.created_at,
        ),
    )


@csrf_exempt
def xpenz_shopping_list_detail(request, shopping_list_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    try:
        shopping_list = _shopping_list_for_user(user, shopping_list_id, access_map)
    except PermissionDenied:
        return _json_error("You do not have access to this shopping list.", status=403)
    if shopping_list.deleted_at:
        return _json_error("Shopping list not found.", status=404)

    item_rows = _active_shopping_items_sorted(shopping_list)
    shopping_list.item_count = len(item_rows)

    return JsonResponse(
        {
            "ok": True,
            "shopping_list": _serialize_shopping_list_entry(shopping_list),
            "items": [_serialize_shopping_item(row) for row in item_rows],
        }
    )


@csrf_exempt
def xpenz_shopping_list_delete(request, shopping_list_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method not in {"POST", "DELETE"}:
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    try:
        shopping_list = _shopping_list_for_user(user, shopping_list_id, access_map)
    except PermissionDenied:
        return _json_error("You do not have access to this shopping list.", status=403)

    shopping_list_title = shopping_list.title or f"Shopping List #{shopping_list.id}"
    was_deleted = bool(shopping_list.deleted_at)
    if not was_deleted:
        now = timezone.now()
        shopping_list.deleted_at = now
        shopping_list.updated_at = now
        shopping_list.save(update_fields=["deleted_at", "updated_at"])
    return JsonResponse(
        {
            "ok": True,
            "shopping_list_id": shopping_list_id,
            "title": shopping_list_title,
            "already_deleted": was_deleted,
        }
    )


@csrf_exempt
def xpenz_shopping_list_changes(request, shopping_list_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    since_raw = (request.GET.get("since") or "").strip()
    timeout_raw = (request.GET.get("timeout") or "").strip()

    since_dt = None
    if since_raw:
        since_dt = parse_datetime(since_raw)
        if since_dt is None:
            return _json_error("Invalid `since` timestamp.", status=400)
        if timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt, timezone.get_current_timezone())

    timeout_seconds = 25
    if timeout_raw:
        try:
            timeout_seconds = int(timeout_raw)
        except (TypeError, ValueError):
            return _json_error("Invalid `timeout` value.", status=400)
    timeout_seconds = max(0, min(timeout_seconds, 25))

    deadline = timezone.now() + timedelta(seconds=timeout_seconds)
    shopping_list = None
    changed = False
    cursor_value = ""
    while True:
        try:
            shopping_list = _shopping_list_for_user(user, shopping_list_id, access_map)
        except PermissionDenied:
            return _json_error("You do not have access to this shopping list.", status=403)

        if shopping_list.deleted_at:
            cursor_dt = (
                shopping_list.updated_at
                or shopping_list.deleted_at
                or shopping_list.created_at
                or timezone.now()
            )
            return JsonResponse(
                {
                    "ok": True,
                    "changed": True,
                    "deleted": True,
                    "cursor": cursor_dt.isoformat(),
                    "shopping_list": _serialize_shopping_list_entry(shopping_list),
                    "items": [],
                }
            )

        cursor_dt = (
            shopping_list.updated_at
            or shopping_list.created_at
            or timezone.now()
        )
        changed = since_dt is None or cursor_dt > since_dt
        cursor_value = cursor_dt.isoformat()
        if changed:
            break
        if timezone.now() >= deadline:
            break
        time.sleep(1)

    item_rows = _active_shopping_items_sorted(shopping_list) if changed else []
    shopping_list.item_count = len(item_rows) if changed else shopping_list.items.filter(
        is_completed=False
    ).count()

    return JsonResponse(
        {
            "ok": True,
            "changed": changed,
            "deleted": False,
            "cursor": cursor_value,
            "shopping_list": _serialize_shopping_list_entry(shopping_list),
            "items": [_serialize_shopping_item(row) for row in item_rows],
        }
    )


@csrf_exempt
def xpenz_shopping_list_items(request, shopping_list_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    try:
        shopping_list = _shopping_list_for_user(user, shopping_list_id, access_map)
    except PermissionDenied:
        return _json_error("You do not have access to this shopping list.", status=403)
    if shopping_list.deleted_at:
        return _json_error("Shopping list not found.", status=404)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    item_name = _normalize_item_text(
        payload.get("item_name") if payload.get("item_name") is not None else request.POST.get("item_name", "")
    )
    item_type = _normalize_item_text(
        payload.get("item_type") if payload.get("item_type") is not None else request.POST.get("item_type", "")
    )
    item_unit = _normalize_item_text(
        payload.get("item_unit") if payload.get("item_unit") is not None else request.POST.get("item_unit", "")
    )
    raw_quantity = payload.get("quantity") if payload.get("quantity") is not None else request.POST.get("quantity")
    quantity = _parse_quantity(raw_quantity or "")
    if quantity is None:
        return _json_error("Quantity must be a positive number.", status=400)
    if not item_name:
        return _json_error("`item_name` is required.", status=400)

    category = _resolve_shopping_category(shopping_list.caterer_id, item_name)
    execution_started_by_other = bool(
        shopping_list.execution_started_at
        and shopping_list.execution_started_by_id
        and shopping_list.execution_started_by_id != user.id
    )
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
        existing.save(update_fields=["quantity", "category", "collaboration_note", "updated_at"])
        item = existing
        merged = True
    else:
        completed_match_exists = ShoppingListItem.objects.filter(
            shopping_list=shopping_list,
            is_completed=True,
            item_name__iexact=item_name,
            item_type__iexact=item_type,
            item_unit__iexact=item_unit,
        ).exists()
        collaboration_note = ""
        if execution_started_by_other and completed_match_exists:
            collaboration_note = "ADDED"
        elif execution_started_by_other and not completed_match_exists:
            collaboration_note = "ADDED"
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name=item_name,
            item_type=item_type,
            item_unit=item_unit,
            quantity=quantity,
            category=category,
            collaboration_note=collaboration_note,
            created_by=user,
        )
        merged = False

    ShoppingList.objects.filter(pk=shopping_list.pk).update(updated_at=timezone.now())
    return JsonResponse(
        {
            "ok": True,
            "shopping_list_id": shopping_list.id,
            "item": _serialize_shopping_item(item),
            "merged": merged,
        },
        status=201 if not merged else 200,
    )


@csrf_exempt
def xpenz_shopping_list_remove_item(request, shopping_list_id, item_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    try:
        shopping_list = _shopping_list_for_user(user, shopping_list_id, access_map)
    except PermissionDenied:
        return _json_error("You do not have access to this shopping list.", status=403)
    if shopping_list.deleted_at:
        return _json_error("Shopping list not found.", status=404)

    item = get_object_or_404(
        ShoppingListItem,
        pk=item_id,
        shopping_list=shopping_list,
        is_completed=False,
    )
    now = timezone.now()
    if not shopping_list.execution_started_at:
        shopping_list.execution_started_at = now
        shopping_list.execution_started_by = user
        shopping_list.save(
            update_fields=["execution_started_at", "execution_started_by", "updated_at"]
        )
    item.is_completed = True
    item.completed_by = user
    item.completed_at = now
    item.save(update_fields=["is_completed", "completed_by", "completed_at", "updated_at"])
    ShoppingList.objects.filter(pk=shopping_list.pk).update(updated_at=now)
    return JsonResponse({"ok": True, "shopping_list_id": shopping_list.id, "item_id": item_id})


@csrf_exempt
def xpenz_shopping_catalog(request):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)
    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    rows = _build_shopping_catalog_queryset(user, access_map)
    payload = _shopping_catalog_payload(rows)
    return JsonResponse(
        {
            "ok": True,
            "items": payload["items"],
            "categories": payload["categories"],
        }
    )


@csrf_exempt
def xpenz_estimate_planner(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate, access_map=access_map):
        return _json_error("You do not have access to this estimate.", status=403)

    if request.method == "GET":
        entries = list(
            estimate.planner_entries.select_related("created_by", "updated_by").order_by(
                "section", "sort_order", "created_at"
            )
        )
        memory_rows = list(
            PlannerFieldMemory.objects.filter(caterer_id=estimate.caterer_id).order_by(
                "-usage_count", "-last_used_at", "value"
            )[:2000]
        )
        return JsonResponse(
            {
                "ok": True,
                "estimate_id": estimate.id,
                "entries": [_serialize_planner_entry(row) for row in entries],
                "memory": _planner_memory_payload(memory_rows),
                "item_catalog": _planner_item_catalog_payload(estimate.caterer_id),
                "icon_overrides": _planner_icon_override_payload(estimate.caterer_id),
                "field_cards": _planner_field_card_payload(estimate.caterer_id),
            }
        )

    if request.method != "POST":
        return _json_error("Method not allowed.", status=405)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    action = _normalize_item_text(payload.get("action") or "upsert").lower()
    if action == "delete":
        raw_entry_id = payload.get("entry_id")
        if not str(raw_entry_id or "").isdigit():
            return _json_error("Invalid entry id.", status=400)
        entry = get_object_or_404(
            EstimatePlannerEntry,
            pk=int(raw_entry_id),
            estimate_id=estimate.id,
        )
        entry.delete()
        return JsonResponse({"ok": True, "deleted_entry_id": int(raw_entry_id)})

    if action == "save_field_cards":
        raw_section = _normalize_item_text(payload.get("section")).upper()
        if raw_section not in PLANNER_SECTION_LABELS:
            return _json_error("Invalid planner section.", status=400)
        group_code = _normalize_item_text(payload.get("group_code", ""))
        item_code = _normalize_item_text(payload.get("item_code", ""))
        field_cards_payload = payload.get("field_cards")
        if not isinstance(field_cards_payload, list):
            field_cards_payload = []
        saved_cards = _save_planner_field_cards(
            estimate=estimate,
            section=raw_section,
            group_code=group_code,
            item_code=item_code,
            payload_rows=field_cards_payload,
            user=user,
        )
        return JsonResponse({"ok": True, "field_cards": saved_cards})

    if action == "save_option_card":
        raw_section = _normalize_item_text(payload.get("section")).upper()
        if raw_section not in PLANNER_SECTION_LABELS:
            return _json_error("Invalid planner section.", status=400)
        group_code = _normalize_item_text(payload.get("group_code", ""))
        item_code = _normalize_item_text(payload.get("item_code", ""))
        item_label = _normalize_item_text(payload.get("item_label", ""))
        try:
            sort_order = int(payload.get("sort_order"))
        except (TypeError, ValueError):
            sort_order = None
        saved_option = _save_planner_option_card(
            estimate=estimate,
            section=raw_section,
            group_code=group_code,
            item_code=item_code,
            item_label=item_label,
            sort_order=sort_order,
            user=user,
        )
        if not saved_option:
            return _json_error("Invalid planner option payload.", status=400)
        return JsonResponse(
            {
                "ok": True,
                "option_card": saved_option,
                "item_catalog": _planner_item_catalog_payload(estimate.caterer_id),
            }
        )

    raw_section = _normalize_item_text(payload.get("section")).upper()
    if raw_section not in PLANNER_SECTION_LABELS:
        return _json_error("Invalid planner section.", status=400)
    group_code = _normalize_item_text(payload.get("group_code", ""))
    item_code = _normalize_item_text(payload.get("item_code", ""))
    notes = _normalize_item_text(payload.get("notes", ""))
    sort_order = 0
    try:
        sort_order = int(payload.get("sort_order") or 0)
    except (TypeError, ValueError):
        sort_order = 0
    sort_order = max(sort_order, 0)
    is_checked = _to_bool(payload.get("is_checked"))
    field_cards_payload = payload.get("field_cards")
    if not isinstance(field_cards_payload, list):
        field_cards_payload = None

    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    cleaned_data = {}
    for raw_key, raw_value in data.items():
        key = _normalize_item_text(raw_key)
        value = _normalize_item_text(raw_value)
        if not key or not value:
            continue
        cleaned_data[key] = value

    raw_entry_id = payload.get("entry_id")
    entry = None
    if str(raw_entry_id or "").isdigit():
        entry = EstimatePlannerEntry.objects.filter(
            pk=int(raw_entry_id),
            estimate_id=estimate.id,
        ).first()
        if not entry:
            return _json_error("Planner entry not found.", status=404)
    if not entry:
        entry = EstimatePlannerEntry(
            estimate=estimate,
            caterer=estimate.caterer,
            created_by=user,
        )

    entry.section = raw_section
    entry.group_code = group_code
    entry.item_code = item_code
    entry.data = cleaned_data
    entry.notes = notes
    entry.is_checked = is_checked
    entry.sort_order = sort_order
    entry.updated_by = user
    entry.save()

    if entry.item_code:
        _save_planner_option_card(
            estimate=estimate,
            section=entry.section,
            group_code=entry.group_code,
            item_code=entry.item_code,
            item_label=payload.get("item_label") or _planner_item_label(
                entry.section, entry.group_code, entry.item_code
            ),
            sort_order=None,
            user=user,
        )

    _record_planner_memory(
        estimate=estimate,
        section=entry.section,
        group_code=entry.group_code,
        item_code=entry.item_code,
        data=entry.data,
    )

    saved_cards = None
    if field_cards_payload is not None:
        saved_cards = _save_planner_field_cards(
            estimate=estimate,
            section=entry.section,
            group_code=entry.group_code,
            item_code=entry.item_code,
            payload_rows=field_cards_payload,
            user=user,
        )

    response_payload = {
        "ok": True,
        "entry": _serialize_planner_entry(entry),
    }
    if saved_cards is not None:
        response_payload["field_cards"] = saved_cards

    return JsonResponse(response_payload, status=201 if not raw_entry_id else 200)


@csrf_exempt
def xpenz_staff_punch(request, token):
    try:
        payload = _load_staff_punch_token(token)
    except signing.SignatureExpired:
        return render(
            request,
            "public/xpenz_staff_punch.html",
            {
                "invalid_token": True,
                "error_message": "This punch link has expired.",
            },
            status=400,
        )
    except signing.BadSignature:
        return render(
            request,
            "public/xpenz_staff_punch.html",
            {
                "invalid_token": True,
                "error_message": "This punch link is invalid or has expired.",
            },
            status=400,
        )

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer"),
        pk=payload.get("estimate_id"),
    )
    role_code = payload.get("role")
    role_labels = dict(STAFF_ROLE_CHOICES)
    if role_code not in role_labels:
        return render(
            request,
            "public/xpenz_staff_punch.html",
            {
                "invalid_token": True,
                "error_message": "Unsupported staff role.",
            },
            status=400,
        )

    hourly_rate = STAFF_ROLE_RATES.get(role_code, Decimal("0.00"))
    active_entries = list(
        estimate.staff_time_entries.filter(role=role_code, punched_out_at__isnull=True).order_by("punched_in_at")
    )
    recent_entries = list(
        estimate.staff_time_entries.filter(role=role_code, punched_out_at__isnull=False)
        .order_by("-punched_out_at")[:20]
    )

    success_message = ""
    error_message = ""

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "punch_in":
            first_name = (request.POST.get("first_name") or "").strip()
            if not first_name:
                error_message = "Enter a first name."
            else:
                EstimateStaffTimeEntry.objects.create(
                    estimate=estimate,
                    role=role_code,
                    worker_first_name=first_name,
                    hourly_rate=hourly_rate,
                    punched_in_at=timezone.now(),
                )
                success_message = f"{first_name} punched in."
        elif action == "punch_out":
            entry_id = (request.POST.get("active_entry_id") or "").strip()
            if not entry_id.isdigit():
                error_message = "Select a worker to punch out."
            else:
                entry = (
                    estimate.staff_time_entries.filter(
                        id=int(entry_id),
                        role=role_code,
                        punched_out_at__isnull=True,
                    ).first()
                )
                if not entry:
                    error_message = "Selected worker is no longer active."
                else:
                    entry.punch_out()
                    entry.save(update_fields=["punched_out_at", "total_hours", "total_cost", "updated_at"])
                    success_message = f"{entry.worker_first_name} punched out."
        else:
            error_message = "Unsupported action."

        active_entries = list(
            estimate.staff_time_entries.filter(role=role_code, punched_out_at__isnull=True).order_by("punched_in_at")
        )
        recent_entries = list(
            estimate.staff_time_entries.filter(role=role_code, punched_out_at__isnull=False)
            .order_by("-punched_out_at")[:20]
        )

    context = {
        "invalid_token": False,
        "estimate": estimate,
        "role_code": role_code,
        "role_label": role_labels[role_code],
        "hourly_rate": hourly_rate,
        "success_message": success_message,
        "error_message": error_message,
        "active_entries": active_entries,
        "recent_entries": recent_entries,
    }
    return render(request, "public/xpenz_staff_punch.html", context)

import logging
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

from django import forms
from django.conf import settings
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
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import stripe

from .forms import ClientInquiryForm
from .models import (
    CatererAccount,
    CatererUserAccess,
    Estimate,
    EstimateExpenseEntry,
    EstimateStaffTimeEntry,
    ShoppingList,
    ShoppingListItem,
    STAFF_ROLE_CHOICES,
    SHOPPING_CATEGORY_CHOICES,
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


def _to_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def _build_shopping_catalog_queryset(user, access_map):
    rows = ShoppingListItem.objects.select_related("shopping_list", "shopping_list__caterer")
    if not user.is_superuser:
        rows = rows.filter(shopping_list__caterer_id__in=list(access_map.keys()))
    return rows


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
    token.rotate(save=False)
    token.last_used_at = timezone.now()
    token.save()

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
    if request.method != "GET":
        return _json_error("Method not allowed.", status=405)

    access_map = _mobile_access_map_for_user(user)
    if not user.is_superuser and not access_map:
        return _json_error("No mobile app access is configured for this user.", status=403)

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

    results = []
    for estimate in estimates:
        event_type = (estimate.event_type or "Event").strip()
        access = _mobile_access_for_caterer(user, estimate.caterer_id, access_map=access_map)
        can_view_billing = bool(access and access.get("can_view_job_billing"))
        can_add_expenses = bool(access and access.get("can_add_expenses"))
        can_manage_staff = bool(access and access.get("can_manage_staff"))
        if user.is_superuser:
            can_view_billing = True
            can_add_expenses = True
            can_manage_staff = True
        results.append(
            {
                "id": estimate.id,
                "estimate_number": estimate.estimate_number,
                "job_name": f"{estimate.customer_name} - {event_type}",
                "customer_name": estimate.customer_name,
                "event_type": estimate.event_type,
                "event_date": estimate.event_date.isoformat() if estimate.event_date else "",
                "event_location": estimate.event_location,
                "caterer_id": estimate.caterer_id,
                "caterer_name": estimate.caterer.name,
                "currency": estimate.currency,
                "grand_total": str(estimate.grand_total) if can_view_billing else "",
                "expense_count": estimate.expense_count,
                "can_view_billing": can_view_billing,
                "can_add_expenses": can_add_expenses,
                "can_manage_staff": can_manage_staff,
            }
        )

    return JsonResponse({"ok": True, "estimates": results})


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

    item_rows = list(shopping_list.items.filter(is_completed=False))
    item_rows = sorted(
        item_rows,
        key=lambda row: (
            SHOPPING_CATEGORY_ORDER.get(row.category, 999),
            (row.item_name or "").lower(),
            (row.item_type or "").lower(),
            (row.item_unit or "").lower(),
            row.created_at,
        ),
    )
    shopping_list.item_count = len(item_rows)

    return JsonResponse(
        {
            "ok": True,
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

    category = _infer_shopping_category(item_name)
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

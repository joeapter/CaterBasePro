import logging
import json
from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login
from django.db.models import Count
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
    Estimate,
    EstimateExpenseEntry,
    TrialRequest,
    XpenzMobileToken,
)

logger = logging.getLogger(__name__)
User = get_user_model()


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


def _can_access_estimate(user, estimate):
    if user.is_superuser:
        return True
    return estimate.caterer.owner_id == user.id


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

    has_caterer = CatererAccount.objects.filter(owner=user).exists()
    if not user.is_superuser and not has_caterer:
        return _json_error("No caterer account linked to this user.", status=403)

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

    estimates = (
        Estimate.objects.select_related("caterer")
        .annotate(expense_count=Count("expense_entries"))
        .order_by("-event_date", "-created_at")
    )
    if not user.is_superuser:
        estimates = estimates.filter(caterer__owner=user)

    results = []
    for estimate in estimates:
        event_type = (estimate.event_type or "Event").strip()
        results.append(
            {
                "id": estimate.id,
                "estimate_number": estimate.estimate_number,
                "job_name": f"{estimate.customer_name} - {event_type}",
                "customer_name": estimate.customer_name,
                "event_type": estimate.event_type,
                "event_date": estimate.event_date.isoformat() if estimate.event_date else "",
                "event_location": estimate.event_location,
                "caterer_name": estimate.caterer.name,
                "currency": estimate.currency,
                "grand_total": str(estimate.grand_total),
                "expense_count": estimate.expense_count,
            }
        )

    return JsonResponse({"ok": True, "estimates": results})


@csrf_exempt
def xpenz_estimate_expenses(request, estimate_id):
    user = _xpenz_authenticated_user(request)
    if not user:
        return _json_error("Authentication required.", status=401)

    estimate = get_object_or_404(
        Estimate.objects.select_related("caterer", "caterer__owner"),
        pk=estimate_id,
    )
    if not _can_access_estimate(user, estimate):
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

    receipt_image = request.FILES.get("receipt_image")
    voice_note = request.FILES.get("voice_note")
    is_manual_only = _to_bool(
        request.POST.get("is_manual_only") or request.POST.get("manual_only") or "0"
    )

    if not is_manual_only:
        if not receipt_image:
            return _json_error("`receipt_image` file is required.", status=400)
        if not voice_note:
            return _json_error("`voice_note` file is required.", status=400)

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

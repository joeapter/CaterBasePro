import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

import stripe

from .forms import ClientInquiryForm
from .models import CatererAccount, TrialRequest

logger = logging.getLogger(__name__)


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

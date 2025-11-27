import random
from django import template
from django.utils import timezone
from django.urls import reverse
from django.db import models

from client_estimates.models import (
    CatererAccount,
    CatererTask,
    ClientInquiry,
)

register = template.Library()

PIPELINE_STATES = [
    ("NEW", "New"),
    ("IN_PROGRESS", "In progress"),
    ("WON", "Won"),
    ("LOST", "Lost"),
]

COMPLIMENTS = [
    "Hey {name}, you are great at your job!",
    "You've got this, {name}. Today is yours!",
    "Clients love working with you, {name}. Keep shining!",
    "{name}, your attention to detail makes every event better.",
    "Fuel up, {name}! There are amazing menus to build today.",
]


def _active_banner(account):
    if not account or not account.dashboard_banner_message:
        return None
    now = timezone.now()
    if account.dashboard_banner_start and account.dashboard_banner_start > now:
        return None
    if account.dashboard_banner_end and account.dashboard_banner_end < now:
        return None
    return account.dashboard_banner_message


@register.simple_tag(takes_context=True)
def get_dashboard_data(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    selected_account = None

    if not user or not user.is_authenticated:
        return {}

    caterer_id = request.GET.get("caterer")
    qs = CatererAccount.objects.all()
    if user.is_superuser:
        if caterer_id:
            selected_account = qs.filter(pk=caterer_id).first()
        if not selected_account:
            selected_account = qs.first()
    else:
        qs = qs.filter(owner=user)
        if caterer_id:
            selected_account = qs.filter(pk=caterer_id).first()
        if not selected_account:
            selected_account = qs.first()

    owner_name = (
        selected_account.primary_contact_name
        or (selected_account.owner.first_name if selected_account and selected_account.owner else "")
        or getattr(user, "first_name", "")
        or getattr(user, "username", "")
    ).strip()

    greeting = random.choice(COMPLIMENTS).format(name=owner_name or user.username)
    banner = _active_banner(selected_account)

    inquiries = []
    tasks = []

    public_inquiry_url = None
    pipeline = []

    if selected_account:
        inquiries = list(
            selected_account.inquiries.filter(status="NEW").order_by("-created_at")[:5]
        )
        tasks = list(
            selected_account.tasks.filter(completed=False).order_by("due_date")[:6]
        )
        counts = {code: 0 for code, _ in PIPELINE_STATES}
        for row in (
            selected_account.inquiries.values("status")
            .order_by()
            .annotate(total=models.Count("id"))
        ):
            counts[row["status"]] = row["total"]
        total_inquiries = sum(counts.values()) or 1  # avoid zero division
        pipeline = [
            {
                "code": code,
                "label": label,
                "count": counts.get(code, 0),
                "percent": round((counts.get(code, 0) / total_inquiries) * 100),
            }
            for code, label in PIPELINE_STATES
        ]
        if selected_account.slug:
            try:
                public_inquiry_url = request.build_absolute_uri(
                    reverse("public_inquiry", kwargs={"caterer_slug": selected_account.slug})
                )
            except Exception:
                public_inquiry_url = None

    return {
        "account": selected_account,
        "greeting": greeting,
        "banner": banner,
        "inquiries": inquiries,
        "tasks": tasks,
        "user": user,
        "public_inquiry_url": public_inquiry_url,
        "pipeline": pipeline,
    }


@register.filter
def digits_only(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())

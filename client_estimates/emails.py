import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _build_recipients(caterer):
    recipients = set()
    if caterer.company_email:
        recipients.add(caterer.company_email)
    if caterer.owner and caterer.owner.email:
        recipients.add(caterer.owner.email)
    return sorted(recipients)


def _menu_sections_for_email(estimate):
    sections = []
    for meal in estimate.meal_sections():
        categories = []
        for category in meal.get("categories", []):
            items = [
                choice.menu_item.name
                for choice in category.get("choices", [])
                if choice.menu_item
            ]
            if items:
                categories.append({"name": category.get("name"), "items": items})
        kids_categories = []
        for category in meal.get("kids_categories", []):
            items = [
                choice.menu_item.name
                for choice in category.get("choices", [])
                if choice.menu_item
            ]
            if items:
                kids_categories.append({"name": category.get("name"), "items": items})
        sections.append(
            {
                "name": meal.get("name"),
                "guest_count": meal.get("guest_count"),
                "guest_count_kids": meal.get("guest_count_kids"),
                "price_per_guest": meal.get("price_per_guest"),
                "price_per_child": meal.get("price_per_child"),
                "total": meal.get("total"),
                "kids_total": meal.get("kids_total"),
                "categories": categories,
                "kids_categories": kids_categories,
            }
        )
    return sections


def _extras_for_email(estimate):
    extras = []
    fx_rate = estimate.exchange_rate or Decimal("1.00")
    guest_count = Decimal(estimate.guest_count or 0)
    for line in estimate.extra_lines.select_related("extra_item"):
        item = line.extra_item
        qty = line.quantity or Decimal("1.00")
        base_price = line.override_price if line.override_price is not None else item.price
        line_total = Decimal("0.00")
        if base_price is not None:
            if item.charge_type == "PER_PERSON":
                line_total = base_price * guest_count * qty
            else:
                line_total = base_price * qty
        extras.append(
            {
                "name": item.name,
                "quantity": qty,
                "charge_type": item.get_charge_type_display(),
                "price": (base_price * fx_rate).quantize(Decimal("0.01")) if base_price is not None else None,
                "total": (line_total * fx_rate).quantize(Decimal("0.01")),
                "notes": line.notes,
            }
        )
    return extras


def _pdf_from_html(html, base_url):
    try:
        from weasyprint import HTML
    except Exception:
        return _text_pdf_from_html(html)
    try:
        return HTML(string=html, base_url=base_url).write_pdf()
    except Exception:
        logger.exception("Failed to render PDF from HTML.")
        return _text_pdf_from_html(html)


def _text_pdf_from_html(html):
    try:
        from fpdf import FPDF
    except Exception:
        return None
    text = strip_tags(html or "").strip()
    if not text:
        text = "Order details unavailable."
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 5, line)
    return pdf.output(dest="S").encode("latin-1")


def send_order_admin_email(
    *,
    estimate,
    request,
    print_html,
    workflow_html,
    print_url,
    workflow_url,
):
    recipients = _build_recipients(estimate.caterer)
    if not recipients:
        return False

    menu_sections = _menu_sections_for_email(estimate)
    extras = _extras_for_email(estimate)

    subject = f"Order #{estimate.estimate_number or estimate.pk} — {estimate.event_type or 'Event'} — {estimate.customer_name}"

    context = {
        "estimate": estimate,
        "menu_sections": menu_sections,
        "extras": extras,
        "print_url": print_url,
        "workflow_url": workflow_url,
    }
    text_body = render_to_string("emails/order_admin.txt", context)
    html_body = render_to_string("emails/order_admin.html", context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=recipients,
    )
    email.attach_alternative(html_body, "text/html")

    base_url = request.build_absolute_uri("/")
    pdf_bytes = _pdf_from_html(print_html, base_url)
    if pdf_bytes:
        email.attach(
            f"order-{estimate.estimate_number or estimate.pk}.pdf",
            pdf_bytes,
            "application/pdf",
        )
    else:
        email.attach(
            f"order-{estimate.estimate_number or estimate.pk}.html",
            print_html,
            "text/html",
        )

    workflow_pdf = _pdf_from_html(workflow_html, base_url)
    if workflow_pdf:
        email.attach(
            f"kitchen-workflow-{estimate.estimate_number or estimate.pk}.pdf",
            workflow_pdf,
            "application/pdf",
        )
    else:
        email.attach(
            f"kitchen-workflow-{estimate.estimate_number or estimate.pk}.html",
            workflow_html,
            "text/html",
        )

    try:
        email.send(fail_silently=False)
    except Exception:
        logger.exception("Failed to send order admin email.")
        return False
    return True

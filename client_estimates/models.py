from decimal import Decimal
import math
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify

# Default footer text appended to every estimate prior to signatures.
DEFAULT_CONTRACT_TERMS = (
    "By approving this estimate you confirm the event details listed above and "
    "agree to remit the deposit listed in the summary to reserve the date. The "
    "remaining balance is due five (5) days before the event unless otherwise "
    "noted in writing. Any changes to guest counts, rentals, or services must be "
    "confirmed in writing. The client is responsible for venue access, utilities, "
    "and permits. Payment signifies acceptance of these terms."
)

DEFAULT_PAYMENT_TERMS = (
    "30% deposit due upon acceptance to reserve date. Remaining balance due on "
    "the event date unless alternate arrangements are approved in writing."
)

PAYMENT_METHOD_CHOICES = [
    ("BANK_TRANSFER", "Bank transfer"),
    ("CASH", "Cash"),
    ("CREDIT_CARD", "Credit card"),
    ("CHECK", "Check"),
]

DOCUMENT_BACKGROUND_CHOICES = [
    ("CLEAN", "Clean white"),
    ("WATERCOLOR_SAGE", "Watercolor sage wash"),
    ("WATERCOLOR_ROSE", "Blush watercolor wash"),
    ("TEXTURED_STONE", "Textured stone wash"),
    ("STENCIL_EUCALYPTUS", "Eucalyptus stencil (greens)"),
    ("STENCIL_BLUSH", "Blush bloom stencil"),
    ("STENCIL_MARBLE", "Marble stencil"),
    ("STENCIL_BOTANICAL", "Botanical parchment stencil"),
    ("STENCIL_WOODLAND", "Rustic board stencil"),
]

DOCUMENT_FONT_CHOICES = [
    ("SERIF", "Classic serif"),
    ("SANS", "Modern sans"),
]

DOCUMENT_SURFACE_CHOICES = [
    ("CARD", "Elevated white cards"),
    ("TRANSPARENT", "Transparent over background"),
]


class CatererAccount(models.Model):
    """
    Tenant model – one per catering business / brand.
    """
    CURRENCY_CHOICES = [
        ("ILS", "Israeli Shekel"),
        ("USD", "US Dollar"),
        ("EUR", "Euro"),
        ("GBP", "British Pound"),
    ]

    name = models.CharField(max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="caterer_accounts",
        help_text="The Django user who owns this catering business.",
    )

    default_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="ILS",
    )

    # Pricing defaults
    default_food_markup = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("3.00")
    )
    staff_hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("50.00")
    )
    staff_tip_per_waiter = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("80.00")
    )

    real_dishes_price_per_person = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("16.00")
    )
    real_dishes_flat_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("400.00")
    )

    primary_contact_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name used for greetings and dashboard personalization.",
    )
    company_phone = models.CharField(max_length=50, blank=True)
    company_email = models.EmailField(blank=True)
    company_address = models.TextField(blank=True)
    bank_details = models.TextField(
        blank=True,
        help_text="Wire / bank instructions that appear on estimates and invoices.",
    )
    brand_logo = models.FileField(upload_to="caterer_logos/", null=True, blank=True)
    brand_primary_color = models.CharField(
        max_length=7,
        default="#0f172a",
        help_text="Primary accent color for PDF headings.",
    )
    brand_accent_color = models.CharField(
        max_length=7,
        default="#b08c6d",
        help_text="Accent color used for highlights and cards.",
    )
    document_background = models.CharField(
        max_length=30,
        choices=DOCUMENT_BACKGROUND_CHOICES,
        default="CLEAN",
    )
    document_font_family = models.CharField(
        max_length=20,
        choices=DOCUMENT_FONT_CHOICES,
        default="SANS",
    )
    document_surface_style = models.CharField(
        max_length=20,
        choices=DOCUMENT_SURFACE_CHOICES,
        default="CARD",
        help_text="Control whether PDFs use floating cards or transparent sections.",
    )
    default_payment_terms = models.TextField(
        blank=True,
        default=DEFAULT_PAYMENT_TERMS,
        help_text="Shown on new estimates unless overridden.",
    )
    estimate_number_counter = models.PositiveIntegerField(
        default=1000,
        help_text="Next estimate/invoice number to issue.",
    )
    dashboard_banner_message = models.TextField(
        blank=True,
        help_text="Message shown on the dashboard. Leave blank when you have nothing to announce.",
    )
    dashboard_banner_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional start datetime for the dashboard message.",
    )
    dashboard_banner_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional end datetime for the dashboard message.",
    )
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_expires_at = models.DateTimeField(null=True, blank=True)
    slug = models.SlugField(
        unique=True,
        blank=True,
        null=True,
        help_text="Used for public inquiry links. Example: palatecatering",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Company profile"
        verbose_name_plural = "Company profiles"

    def __str__(self):
        return self.name

    def get_brand_font_stack(self):
        if self.document_font_family == "SERIF":
            return '"Georgia", "Times New Roman", serif'
        return '"Helvetica Neue", Arial, "Segoe UI", sans-serif'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "caterer"
            slug_candidate = base_slug
            counter = 1
            while CatererAccount.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                slug_candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug_candidate
        now = timezone.now()
        if not self.trial_started_at:
            self.trial_started_at = now
        if not self.trial_expires_at and self.trial_started_at:
            self.trial_expires_at = self.trial_started_at + timedelta(days=30)
        super().save(*args, **kwargs)


class MenuCategory(models.Model):
    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="menu_categories"
    )
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Menu categories"

    def __str__(self):
        return f"{self.caterer.name} – {self.name}"


class MenuItem(models.Model):
    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="menu_items"
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Internal cost per serving (one person)
    cost_per_serving = models.DecimalField(max_digits=8, decimal_places=2)

    # Markup (e.g. 3.00 for cost x3)
    markup = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("3.00")
    )

    # For items where you serve half a portion, etc.
    default_servings_per_person = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.00")
    )

    is_active = models.BooleanField(default=True)

    def price_per_serving(self) -> Decimal:
        return (self.cost_per_serving * self.markup).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.name} ({self.caterer.name})"


class MenuTemplate(models.Model):
    """
    A named selection of menu items for quick reuse (e.g. 'Bar Mitzvah Buffet').
    """
    caterer = models.ForeignKey(
        CatererAccount,
        on_delete=models.CASCADE,
        related_name="templates",
    )
    name = models.CharField(max_length=200)
    items = models.ManyToManyField(MenuItem, related_name="templates")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("caterer", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.caterer.name})"


class ExtraItem(models.Model):
    """
    Decor / rental / add-on items (popcorn machine, projector, etc).
    """
    CATEGORY_CHOICES = [
        ("DECOR", "Decor"),
        ("RENTAL", "Rental"),
        ("SERVICE", "Service"),
        ("OTHER", "Other"),
    ]

    CHARGE_TYPE_CHOICES = [
        ("PER_EVENT", "Per event"),
        ("PER_PERSON", "Per person"),
    ]

    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="extra_items"
    )
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="RENTAL"
    )
    charge_type = models.CharField(
        max_length=20, choices=CHARGE_TYPE_CHOICES, default="PER_EVENT"
    )

    cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Internal cost",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Customer price (per person or per event, depending on charge type)",
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.caterer.name})"


class Estimate(models.Model):
    """
    One estimate / quote for a customer event.
    """
    CURRENCY_CHOICES = CatererAccount.CURRENCY_CHOICES

    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="estimates"
    )

    # Customer & event info
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=50, blank=True)
    customer_email = models.EmailField(blank=True)

    event_type = models.CharField(max_length=100, blank=True)
    event_date = models.DateField(default=timezone.now)
    event_location = models.CharField(max_length=255, blank=True)
    guest_count = models.PositiveIntegerField(default=0)
    guest_count_kids = models.PositiveIntegerField(
        default=0,
        help_text="Kids count for separate pricing when using kids menu category.",
    )

    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="ILS"
    )

    # Included disposables
    include_premium_plastic = models.BooleanField(default=True)
    include_premium_tablecloths = models.BooleanField(default=True)

    # Real dishes option
    wants_real_dishes = models.BooleanField(default=False)
    real_dishes_price_per_person = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    real_dishes_flat_fee = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Staff
    staff_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("6.00")
    )
    extra_waiters = models.PositiveIntegerField(default=0)
    staff_hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    staff_tip_per_waiter = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    meal_plan = models.JSONField(
        default=list,
        blank=True,
        help_text="List of meal names (e.g. Friday Dinner, Shabbos Lunch) used to organize menu selections.",
    )
    estimate_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Sequential estimate/invoice number for client-facing docs.",
    )

    # Stored totals (we can recalc in save())
    food_price_per_person = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    extras_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    staff_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    dishes_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    grand_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deposit_amount = models.DecimalField(
        "Deposit due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    balance_due = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    manual_meal_totals = models.JSONField(
        blank=True,
        default=dict,
        help_text="Stores manual per-meal price overrides.",
    )

    notes_internal = models.TextField(blank=True)
    notes_for_customer = models.TextField(blank=True)
    payment_instructions = models.TextField(
        blank=True,
        help_text="Shown on invoices and PDF downloads so clients know how to pay.",
    )
    payment_terms = models.TextField(
        blank=True,
        help_text="High-level schedule (e.g. deposit %, final due date).",
    )
    deposit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("30.00"),
        help_text="Used to calculate deposit in the PDF summary.",
    )
    payment_method = models.CharField(
        max_length=30,
        blank=True,
        choices=PAYMENT_METHOD_CHOICES,
        help_text="Primary payment method for this document.",
    )
    is_invoice = models.BooleanField(
        default=False,
        help_text="Set automatically when the quote is converted into an invoice.",
    )
    contract_terms = models.TextField(
        blank=True,
        default=DEFAULT_CONTRACT_TERMS,
        help_text="Terms + conditions shown at the bottom of the summary/PDF.",
    )
    terms_acknowledged = models.BooleanField(
        default=False,
        help_text="Check when the client has acknowledged the contract terms.",
    )
    signature_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name of the person signing/approving the estimate.",
    )
    signature_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title to show under the signature line.",
    )
    signature_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the estimate or invoice was accepted.",
    )
    is_ala_carte = models.BooleanField(
        default=False,
        help_text="Skip staff/dishes/plastic info – food delivery only (a la carte).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("caterer", "estimate_number")

    def __str__(self):
        return f"{self.customer_name} – {self.event_type} ({self.event_date})"

    # ---- Helpers ----

    def _get_staff_hourly_rate(self) -> Decimal:
        return (
            self.staff_hourly_rate
            or self.caterer.staff_hourly_rate
            or Decimal("0.00")
        )

    def _get_staff_tip_per_waiter(self) -> Decimal:
        return (
            self.staff_tip_per_waiter
            or self.caterer.staff_tip_per_waiter
            or Decimal("0.00")
        )

    def base_waiter_count(self) -> int:
        guests = self.guest_count or 0
        if guests == 0:
            return 0
        if guests <= 50:
            return 2
        elif guests <= 75:
            return 3
        elif guests <= 100:
            return 4
        extra = max(guests - 100, 0)
        return 4 + math.ceil(extra / 25)

    def total_waiter_count(self) -> int:
        return self.base_waiter_count() + (self.extra_waiters or 0)

    def _normalize_meal_plan(self):
        plan = [name.strip() for name in (self.meal_plan or []) if name and name.strip()]
        if not plan:
            plan = ["Signature Menu"]
        return plan

    def default_meal_name(self):
        return self._normalize_meal_plan()[0]

    def get_meal_plan(self):
        return self._normalize_meal_plan()

    def calc_food_price_per_person(self) -> Decimal:
        total = Decimal("0.00")
        for section in self.meal_sections():
            total += section["price_per_guest"]
        return total.quantize(Decimal("0.01"))

    def calc_extras_total(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.extra_lines.select_related("extra_item"):
            if line.override_price is not None:
                total += line.override_price
            else:
                item = line.extra_item
                qty = line.quantity or Decimal("1.0")
                if item.charge_type == "PER_PERSON":
                    total += item.price * Decimal(self.guest_count or 0) * qty
                else:
                    total += item.price * qty
        return total.quantize(Decimal("0.01"))

    def calc_staff_total(self) -> Decimal:
        if self.is_ala_carte:
            return Decimal("0.00")
        waiters = self.total_waiter_count()
        if waiters == 0:
            return Decimal("0.00")
        hours = self.staff_hours or Decimal("0.00")
        rate = self._get_staff_hourly_rate()
        tip = self._get_staff_tip_per_waiter()
        staff_pay = rate * hours * waiters
        staff_tip = tip * waiters
        return (staff_pay + staff_tip).quantize(Decimal("0.01"))

    def calc_dishes_total(self) -> Decimal:
        if self.is_ala_carte:
            return Decimal("0.00")
        if not self.wants_real_dishes:
            return Decimal("0.00")
        per_person = (
            self.real_dishes_price_per_person
            or self.caterer.real_dishes_price_per_person
        )
        flat = self.real_dishes_flat_fee or self.caterer.real_dishes_flat_fee
        guests = Decimal(self.guest_count or 0)
        total = per_person * guests + flat
        return total.quantize(Decimal("0.01"))

    def recalc_totals(self):
        if not self.pk:
            self.food_price_per_person = Decimal("0.00")
            self.extras_total = Decimal("0.00")
            self.staff_total = Decimal("0.00")
            self.dishes_total = Decimal("0.00")
            self.grand_total = Decimal("0.00")
            self.deposit_amount = Decimal("0.00")
            self.balance_due = Decimal("0.00")
            return

        food_pp = self.calc_food_price_per_person()
        extras = self.calc_extras_total()
        staff = self.calc_staff_total()
        dishes = self.calc_dishes_total()

        guests = Decimal(self.guest_count or 0)
        food_total = food_pp * guests

        grand = food_total + extras + staff + dishes
        deposit_rate = (self.deposit_percentage or Decimal("0.00")) / Decimal("100.0")
        deposit = (grand * deposit_rate).quantize(Decimal("0.01"))
        balance = grand - deposit

        self.food_price_per_person = food_pp
        self.extras_total = extras
        self.staff_total = staff
        self.dishes_total = dishes
        self.grand_total = grand.quantize(Decimal("0.01"))
        self.deposit_amount = deposit
        self.balance_due = balance.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if not self.payment_terms and self.caterer_id:
            self.payment_terms = self.caterer.default_payment_terms
        self.recalc_totals()
        super().save(*args, **kwargs)

    def meal_sections(self):
        """
        Returns a list of dicts with meal name, grouped categories, and totals for display.
        """
        plan = self.get_meal_plan()
        default_meal = plan[0]
        if not self.pk:
            return [
                {
                    "name": name,
                    "categories": [],
                    "kids_categories": [],
                    "price_per_guest": Decimal("0.00"),
                    "price_per_child": Decimal("0.00"),
                    "total": Decimal("0.00"),
                    "kids_total": Decimal("0.00"),
                }
                for name in plan
            ]
        choices = list(
            self.food_choices.filter(included=True).select_related("menu_item", "menu_item__category")
        )
        sections = []
        overrides = self.manual_meal_totals or {}
        guest_count = Decimal(self.guest_count or 0)
        guest_count_kids = Decimal(self.guest_count_kids or 0)
        for meal_name in plan:
            meal_choices = [
                ch for ch in choices if (ch.meal_name or default_meal) == meal_name
            ]
            categories = {}
            kids_categories = {}
            for ch in meal_choices:
                category_name = (
                    ch.menu_item.category.name if ch.menu_item.category else "Chef's Selection"
                )
                target = categories
                if ch.menu_item and ch.menu_item.category and "kid" in ch.menu_item.category.name.lower():
                    target = kids_categories
                target.setdefault(category_name, []).append(ch)

            def _price_for(items):
                price_pp_local = Decimal("0.00")
                for ch in items:
                    mi = ch.menu_item
                    servings = ch.servings_per_person or mi.default_servings_per_person
                    cost_per_person = mi.cost_per_serving * servings
                    price_pp_local += cost_per_person * mi.markup
                return price_pp_local.quantize(Decimal("0.01"))

            adult_items = [c for items in categories.values() for c in items]
            kids_items = [c for items in kids_categories.values() for c in items]

            price_pp = _price_for(adult_items)
            price_pp_kids = _price_for(kids_items)
            override_value = overrides.get(meal_name)
            if override_value not in (None, ""):
                try:
                    price_pp = Decimal(str(override_value)).quantize(Decimal("0.01"))
                except Exception:
                    pass

            sections.append(
                {
                    "name": meal_name,
                    "categories": [
                        {"name": cat, "choices": items}
                        for cat, items in categories.items()
                    ],
                    "kids_categories": [
                        {"name": f"{cat} (Kids)", "choices": items}
                        for cat, items in kids_categories.items()
                    ],
                    "price_per_guest": price_pp,
                    "price_per_child": price_pp_kids,
                    "total": (price_pp * guest_count).quantize(Decimal("0.01")),
                    "kids_total": (price_pp_kids * guest_count_kids).quantize(Decimal("0.01")),
                }
            )
        return sections

    def meal_grand_total(self):
        total = Decimal("0.00")
        for section in self.meal_sections():
            total += section["total"] + section.get("kids_total", Decimal("0.00"))
        return total.quantize(Decimal("0.01")) if total else Decimal("0.00")


class EstimateFoodChoice(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="food_choices"
    )
    menu_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name="estimate_choices"
    )
    meal_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional meal label (e.g. Friday Dinner) for multi-meal estimates.",
    )
    included = models.BooleanField(default=True)
    servings_per_person = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="If blank, uses menu item's default",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("estimate", "menu_item", "meal_name")

    def __str__(self):
        return f"{self.menu_item.name} for {self.estimate}"


class EstimateExtraItem(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE, related_name="extra_lines"
    )
    extra_item = models.ForeignKey(
        ExtraItem, on_delete=models.CASCADE, related_name="estimate_lines"
    )
    quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("1.00")
    )
    override_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="If set, replaces automatic price calculation",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Extra line"
        verbose_name_plural = "Extra lines"

    def __str__(self):
        return f"{self.extra_item.name} for {self.estimate}"


class TastingAppointment(models.Model):
    """
    Scheduler entry for tastings or meetings.
    """

    TYPE_CHOICES = [
        ("TASTING", "Tasting"),
        ("MEETING", "Meeting"),
    ]
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("COMPLETED", "Completed"),
        ("CANCELED", "Canceled"),
    ]

    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="appointments"
    )
    estimate = models.ForeignKey(
        Estimate,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="appointments",
        help_text="Optional link to an estimate so client info stays in sync.",
    )
    title = models.CharField(max_length=200)
    start_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    appointment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="TASTING")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="SCHEDULED")
    location = models.CharField(max_length=255, blank=True)
    client_name = models.CharField(max_length=200, blank=True)
    client_email = models.EmailField(blank=True)
    client_phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_at"]
        verbose_name = "Tasting / meeting"
        verbose_name_plural = "Tastings / meetings"

    def __str__(self):
        return f"{self.title} ({self.caterer.name})"


class TrialRequest(models.Model):
    """
    Public 30-day trial request captured from the marketing page.
    """

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Trial request"
        verbose_name_plural = "Trial requests"

    def __str__(self):
        return f"{self.name} ({self.email or self.phone})"


class TrialPaymentLink(models.Model):
    """
    Optional payment link for expired trials.
    """

    caterer = models.OneToOneField(
        CatererAccount, on_delete=models.CASCADE, related_name="trial_payment_link"
    )
    url = models.URLField(help_text="Payment link to restart after trial.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.caterer.name} payment link"


class ClientProfile(models.Model):
    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="clients"
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    birthday = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("caterer", "email", "phone")

    def __str__(self):
        return f"{self.name} ({self.caterer.name})"


class ClientInquiry(models.Model):
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("IN_PROGRESS", "In progress"),
        ("WON", "Won"),
        ("LOST", "Lost"),
    ]

    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="inquiries"
    )
    contact_name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    preferred_contact_method = models.CharField(max_length=20, blank=True)
    event_type = models.CharField(max_length=100, blank=True)
    event_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="NEW"
    )
    converted_to_client = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.contact_name} – {self.caterer.name}"


class CatererTask(models.Model):
    caterer = models.ForeignKey(
        CatererAccount, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    related_inquiry = models.ForeignKey(
        ClientInquiry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["completed", "due_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.caterer.name})"

from decimal import Decimal

from .models import ExtraItem, EstimateExtraItem, MenuCategory, MenuItem

KIDDUSH_PLANNING_FEE_NAME = "Kiddush planning fee"
KIDDUSH_PLANNING_FEE_AMOUNT = Decimal("3500.00")

KIDDUSH_MENU_SECTIONS = [
    {
        "category": "Food - Palate",
        "sort_order": 10,
        "items": [
            {"name": "Rolls / buns", "serving": "1 Roll", "pieces": "1", "cost": "2.50"},
            {"name": "Assorted Bakery Items", "serving": "Box Of 30", "pieces": "30", "cost": "70.00"},
            {"name": "Parve Chulent", "serving": "Pot", "pieces": "50", "cost": "650.00"},
            {"name": "Meat Chulent", "serving": "Pot", "pieces": "75", "cost": "1500.00"},
            {"name": "Potato Kugel", "serving": "Gastro Tray", "pieces": "90", "cost": "180.00"},
            {"name": "Yerushalmi Kugel", "serving": "Pot", "pieces": "90", "cost": "180.00"},
            {"name": "Herring", "serving": "1 kg", "pieces": "25", "cost": "160.00"},
            {"name": "Salads - Coleslaw", "serving": "1", "pieces": "25", "cost": "180.00"},
            {"name": "Salads - Nish Nushim", "serving": "1", "pieces": "25", "cost": "180.00"},
            {"name": "Salads - Pecan", "serving": "1", "pieces": "25", "cost": "220.00"},
            {"name": "Salads - Quinoua / Rstd Veggie", "serving": "1", "pieces": "25", "cost": "210.00"},
            {"name": "Potatoe Salad", "serving": "1", "pieces": "25", "cost": "180.00"},
            {"name": "Sesame Noodles", "serving": "1", "pieces": "25", "cost": "180.00"},
            {"name": "Salmon Sushi Salad", "serving": "1", "pieces": "25", "cost": "280.00"},
            {"name": "Sushi Salad", "serving": "1", "pieces": "25", "cost": "220.00"},
            {"name": "Garden Smoked Salmon Salad", "serving": "1", "pieces": "25", "cost": "280.00"},
            {"name": "Pasta Salad", "serving": "1", "pieces": "25", "cost": "180.00"},
            {"name": "Greek Salad", "serving": "1", "pieces": "25", "cost": "210.00"},
            {"name": "Sides Of Salmon", "serving": "1", "pieces": "12", "cost": "280.00"},
            {"name": "Meat Boards", "serving": "1 Board", "pieces": "25", "cost": "500.00"},
            {"name": "Twist Mini Bar - Petit Fours", "serving": "3 Trays", "pieces": "180", "cost": "650.00"},
            {"name": "Nosh", "serving": "Asst", "pieces": "75", "cost": "200.00"},
            {"name": "Candy", "serving": "Asst", "pieces": "75", "cost": "400.00"},
            {"name": "Grape Juice (Kedem)", "serving": "1 Bottle", "pieces": "1", "cost": "38.00"},
        ],
    },
    {
        "category": "Desserts - Amy",
        "sort_order": 20,
        "items": [
            {"name": "Cupcakes", "serving": "Single Piece", "pieces": "1", "cost": "18.00"},
            {"name": "Cakesicals", "serving": "Single Piece", "pieces": "1", "cost": "18.00"},
            {"name": "Personalized Cookies (hand painted)", "serving": "Single Piece", "pieces": "1", "cost": "18.00"},
        ],
    },
    {
        "category": "Desserts - Bake My Day",
        "sort_order": 30,
        "items": [
            {"name": "Assorted Cookies", "serving": "Box of 20", "pieces": "20", "cost": "45.00"},
            {"name": "Brownies", "serving": "Tray of 25", "pieces": "25", "cost": "75.00"},
            {"name": "Chocolate Covered Pretzles", "serving": "Box of 15", "pieces": "15", "cost": "90.00"},
            {"name": "Chocolate Peanutbutter Bars", "serving": "Box of 20", "pieces": "20", "cost": "45.00"},
            {"name": "Lemon Merangue Tartlets", "serving": "Box of 24", "pieces": "24", "cost": "240.00"},
            {"name": "Logo Cookies", "serving": "Single Piece", "pieces": "1", "cost": "12.00"},
            {"name": "Mini Cupcakes", "serving": "Tray of 30", "pieces": "30", "cost": "120.00"},
            {"name": "Mini Eclairs", "serving": "Box of 28", "pieces": "28", "cost": "175.00"},
            {"name": "Mousse Cups", "serving": "Single Piece", "pieces": "1", "cost": "9.00"},
            {"name": "Personalized Cookies (printed)", "serving": "Single Piece", "pieces": "1", "cost": "12.00"},
            {"name": "Pretzle Peanutbutter Chocolate Squares", "serving": "Box of 25", "pieces": "25", "cost": "40.00"},
            {"name": "Printed Nishikot", "serving": "Box of 48", "pieces": "48", "cost": "120.00"},
            {"name": "Rice Crispie Bars", "serving": "Box of 36", "pieces": "36", "cost": "72.00"},
        ],
    },
    {
        "category": "Desserts - Michal Rabinowitz",
        "sort_order": 40,
        "items": [
            {"name": "Cupcakes", "serving": "Single Piece", "pieces": "1", "cost": "12.00"},
            {"name": "Cakesicals", "serving": "Single Piece", "pieces": "1", "cost": "15.00"},
        ],
    },
    {
        "category": "Desserts - Pri Hadar",
        "sort_order": 50,
        "items": [
            {"name": "Fruit Cups", "serving": "Single Piece", "pieces": "1", "cost": "11.00"},
            {"name": "Veggi Cups", "serving": "Single Piece", "pieces": "1", "cost": "9.00"},
            {"name": "Fruit Platter (medium)", "serving": "Medium Tray", "pieces": "50", "cost": "260.00"},
        ],
    },
    {
        "category": "Drinks",
        "sort_order": 60,
        "items": [
            {"name": "Coke Zero", "serving": "Case of 6", "pieces": "6", "cost": "48.00"},
            {"name": "Coke", "serving": "Case of 6", "pieces": "6", "cost": "48.00"},
            {"name": "Water (2 liter bottles)", "serving": "Case of 6", "pieces": "6", "cost": "13.90"},
            {"name": "Flavoured Zelcer", "serving": "Case of 4", "pieces": "4", "cost": "12.00"},
            {"name": "Spring Juices & Teas", "serving": "Single Bottle", "pieces": "1", "cost": "6.75"},
        ],
    },
]


def _description_for_serving(serving_text: str) -> str:
    text = (serving_text or "").strip()
    if not text:
        return ""
    if not any(ch.isalpha() for ch in text):
        return ""
    return f"Serving: {text}"


def ensure_kiddush_menu(caterer):
    if not caterer:
        return
    default_markup = caterer.default_food_markup or Decimal("3.00")
    for section in KIDDUSH_MENU_SECTIONS:
        category, created = MenuCategory.objects.get_or_create(
            caterer=caterer,
            name=section["category"],
            defaults={"sort_order": section["sort_order"]},
        )

        for idx, item in enumerate(section["items"], start=1):
            pieces = Decimal(str(item["pieces"]))
            cost = Decimal(str(item["cost"]))
            cost_per_serving = cost
            if pieces:
                cost_per_serving = (cost / pieces).quantize(Decimal("0.01"))
            description = _description_for_serving(item.get("serving", ""))

            MenuItem.objects.get_or_create(
                caterer=caterer,
                category=category,
                name=item["name"],
                menu_type="KIDDUSH",
                defaults={
                    "description": description,
                    "sort_order_override": idx,
                    "cost_per_serving": cost_per_serving,
                    "markup": default_markup,
                    "default_servings_per_person": Decimal("1.00"),
                    "is_active": True,
                },
            )


def ensure_kiddush_planning_fee(caterer):
    if not caterer:
        return None
    fee_item, _ = ExtraItem.objects.get_or_create(
        caterer=caterer,
        name=KIDDUSH_PLANNING_FEE_NAME,
        defaults={
            "category": "SERVICE",
            "charge_type": "PER_EVENT",
            "price": KIDDUSH_PLANNING_FEE_AMOUNT,
            "cost": Decimal("0.00"),
            "is_active": False,
        },
    )
    return fee_item


def ensure_kiddush_planning_fee_line(estimate):
    if not estimate or not estimate.caterer_id:
        return
    fee_item = ensure_kiddush_planning_fee(estimate.caterer)
    if not fee_item:
        return
    line, created = EstimateExtraItem.objects.get_or_create(
        estimate=estimate,
        extra_item=fee_item,
        defaults={"quantity": Decimal("1.00")},
    )
    if not created and line.quantity != Decimal("1.00"):
        line.quantity = Decimal("1.00")
        line.save(update_fields=["quantity"])

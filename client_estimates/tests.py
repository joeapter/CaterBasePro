from decimal import Decimal
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CatererAccount,
    CatererUserAccess,
    Estimate,
    EstimateFoodChoice,
    EstimateExpenseEntry,
    MenuCategory,
    MenuItem,
    ShoppingList,
    ShoppingListItem,
    EstimateStaffTimeEntry,
    XpenzMobileToken,
)


class XpenzApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="secret123",
            is_staff=True,
        )
        self.other_user = user_model.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="secret123",
            is_staff=True,
        )
        self.app_user = user_model.objects.create_user(
            username="appstaff@example.com",
            email="appstaff@example.com",
            password="secret123",
            is_staff=True,
        )

        self.caterer = CatererAccount.objects.create(
            name="Owner Catering",
            owner=self.user,
        )
        self.other_caterer = CatererAccount.objects.create(
            name="Other Catering",
            owner=self.other_user,
        )

        self.estimate = Estimate.objects.create(
            caterer=self.caterer,
            customer_name="Client A",
            event_type="Wedding",
            estimate_number=1001,
            guest_count=50,
            grand_total=Decimal("5000.00"),
        )
        self.newer_estimate = Estimate.objects.create(
            caterer=self.caterer,
            customer_name="Client A2",
            event_type="Wedding",
            estimate_number=1002,
            guest_count=60,
            grand_total=Decimal("6100.00"),
        )
        self.other_estimate = Estimate.objects.create(
            caterer=self.other_caterer,
            customer_name="Client B",
            event_type="Bar Mitzvah",
            estimate_number=2001,
            guest_count=80,
            grand_total=Decimal("8000.00"),
        )
        CatererUserAccess.objects.create(
            caterer=self.caterer,
            user=self.app_user,
            can_access_mobile_app=True,
            can_add_expenses=True,
            can_view_job_billing=False,
            can_manage_staff=True,
        )

    def _login_and_get_token(self, username="owner@example.com"):
        response = self.client.post(
            reverse("xpenz_mobile_login"),
            data=json.dumps({"username": username, "password": "secret123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["token"]

    def test_login_returns_token(self):
        response = self.client.post(
            reverse("xpenz_mobile_login"),
            data=json.dumps({"username": "owner@example.com", "password": "secret123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("token", payload)

    def test_login_reuses_existing_mobile_token(self):
        first_token = self._login_and_get_token()
        second_token = self._login_and_get_token()
        self.assertEqual(first_token, second_token)
        self.assertEqual(
            XpenzMobileToken.objects.filter(user=self.user).count(),
            1,
        )

        response = self.client.get(
            reverse("xpenz_estimate_list"),
            HTTP_AUTHORIZATION=f"Bearer {first_token}",
        )
        self.assertEqual(response.status_code, 200)

    def test_estimate_list_is_scoped_to_owner(self):
        token = self._login_and_get_token()
        response = self.client.get(
            reverse("xpenz_estimate_list"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        ids = [row["id"] for row in payload["estimates"]]
        self.assertIn(self.estimate.id, ids)
        self.assertIn(self.newer_estimate.id, ids)
        self.assertNotIn(self.other_estimate.id, ids)

    def test_estimate_list_orders_by_estimate_number_desc(self):
        token = self._login_and_get_token()
        response = self.client.get(
            reverse("xpenz_estimate_list"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = [row["id"] for row in payload["estimates"]]
        self.assertGreaterEqual(len(ids), 2)
        self.assertEqual(ids[0], self.newer_estimate.id)

    def test_app_user_sees_jobs_but_not_billing_totals(self):
        token = self._login_and_get_token("appstaff@example.com")
        response = self.client.get(
            reverse("xpenz_estimate_list"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload["estimates"]
        self.assertTrue(rows)
        first = rows[0]
        self.assertIn("job_name", first)
        self.assertEqual(first["grand_total"], "")
        self.assertFalse(first["can_view_billing"])
        self.assertTrue(first["can_add_expenses"])
        self.assertTrue(first["can_manage_staff"])

    def test_estimate_print_html_endpoint_returns_admin_render(self):
        token = self._login_and_get_token()
        response = self.client.get(
            reverse("xpenz_estimate_print_html", args=[self.estimate.id]),
            {"variant": "estimate"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, self.estimate.customer_name)

    def test_estimate_print_html_endpoint_supports_workflow_variant(self):
        token = self._login_and_get_token()
        response = self.client.get(
            reverse("xpenz_estimate_print_html", args=[self.estimate.id]),
            {"variant": "workflow"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "Kitchen Workflow")

    def test_estimate_print_html_endpoint_injects_mobile_a4_clamp(self):
        token = self._login_and_get_token()
        response = self.client.get(
            reverse("xpenz_estimate_print_html", args=[self.estimate.id]),
            {"variant": "estimate"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, 'id="xpenz-mobile-print-clamp"')
        self.assertContains(response, "@media all")

    def test_admin_workflow_print_includes_menu_item_notes(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)

        category = MenuCategory.objects.create(
            caterer=self.caterer,
            name="Appetizers",
            sort_order=1,
        )
        menu_item = MenuItem.objects.create(
            caterer=self.caterer,
            category=category,
            name="Burger Slider",
            cost_per_serving=Decimal("1.00"),
            markup=Decimal("1.00"),
        )
        EstimateFoodChoice.objects.create(
            estimate=self.estimate,
            menu_item=menu_item,
            meal_name="Friday Night",
            included=True,
            notes="No sesame",
        )
        self.estimate.meal_plan = ["Friday Night"]
        self.estimate.save(update_fields=["meal_plan"])

        response = self.client.get(
            reverse("admin:client_estimates_estimate_workflow", args=[self.estimate.id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Burger Slider")
        self.assertContains(response, "(No sesame)")

    def test_estimate_builder_saves_per_meal_overrides(self):
        token = self._login_and_get_token()
        self.estimate.meal_plan = ["Friday Night", "Shabbos Day"]
        self.estimate.save(update_fields=["meal_plan"])

        response = self.client.post(
            reverse("xpenz_estimate_builder", args=[self.estimate.id]),
            data=json.dumps(
                {
                    "estimate": {
                        "manual_meal_totals": {
                            "Friday Night": "145.5",
                            "Shabbos Day": "155.25",
                        },
                        "meal_guest_overrides": {
                            "Friday Night": {"adults": "100", "kids": "12"},
                            "Shabbos Day": {"adults": "96"},
                        },
                    }
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.estimate.refresh_from_db()
        self.assertEqual(
            self.estimate.manual_meal_totals,
            {
                "Friday Night": "145.50",
                "Shabbos Day": "155.25",
            },
        )
        self.assertEqual(
            self.estimate.meal_guest_overrides,
            {
                "Friday Night": {"adults": 100, "kids": 12},
                "Shabbos Day": {"adults": 96},
            },
        )
        payload = response.json()
        self.assertEqual(payload["estimate"]["manual_meal_totals"]["Friday Night"], "145.50")
        self.assertEqual(payload["estimate"]["meal_guest_overrides"]["Friday Night"]["adults"], 100)

    def test_expense_upload_requires_receipt_file(self):
        token = self._login_and_get_token()
        response = self.client.post(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            data={"note_text": "Missing files"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 400)

    def test_expense_upload_and_list(self):
        token = self._login_and_get_token()
        receipt = SimpleUploadedFile(
            "receipt.jpg",
            b"fake-jpg-content",
            content_type="image/jpeg",
        )
        voice = SimpleUploadedFile(
            "voice.m4a",
            b"fake-audio-content",
            content_type="audio/m4a",
        )
        upload_response = self.client.post(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            data={
                "receipt_image": receipt,
                "voice_note": voice,
                "note_text": "Taxi to market",
                "voice_note_duration_seconds": "12",
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(upload_response.status_code, 201)
        self.assertTrue(upload_response.json()["ok"])

        list_response = self.client.get(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(list_response.status_code, 200)
        entries = list_response.json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["note_text"], "Taxi to market")
        self.assertEqual(entries[0]["expense_text"], "")

    def test_expense_upload_allows_receipt_without_voice(self):
        token = self._login_and_get_token()
        receipt = SimpleUploadedFile(
            "receipt-only.jpg",
            b"fake-jpg-content",
            content_type="image/jpeg",
        )
        upload_response = self.client.post(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            data={
                "receipt_image": receipt,
                "note_text": "Receipt only",
                "expense_amount": "14.00",
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(upload_response.status_code, 201)
        payload = upload_response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["entry"]["has_receipt_image"])
        self.assertFalse(payload["entry"]["has_voice_note"])

    def test_app_user_can_add_expense_when_allowed(self):
        token = self._login_and_get_token("appstaff@example.com")
        receipt = SimpleUploadedFile(
            "staff-receipt.jpg",
            b"fake-jpg-content",
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            data={
                "receipt_image": receipt,
                "expense_text": "Staff fuel",
                "expense_amount": "12.00",
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry"]["expense_text"], "Staff fuel")

    def test_manual_expense_without_files(self):
        token = self._login_and_get_token()
        response = self.client.post(
            reverse("xpenz_estimate_expenses", args=[self.estimate.id]),
            data={
                "is_manual_only": "1",
                "expense_text": "Parking",
                "expense_amount": "28.50",
                "note_text": "Added manually",
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["entry"]["is_manual_only"])
        self.assertEqual(payload["entry"]["expense_text"], "Parking")
        self.assertEqual(payload["entry"]["expense_amount"], "28.50")

    def test_per_meal_wait_staff_count_overrides_staff_total(self):
        estimate = self.estimate
        estimate.staff_hourly_rate = Decimal("50.00")
        estimate.staff_tip_per_waiter = Decimal("80.00")
        estimate.meal_plan = ["Friday Night", "Shabbos Day"]
        estimate.meal_service_details = {
            "Friday Night": {
                "staff_hours": "2",
                "wait_staff_count": 1,
                "staff_tip_per_waiter": "80",
            },
            "Shabbos Day": {
                "staff_hours": "4",
                "wait_staff_count": 3,
                "staff_tip_per_waiter": "80",
            },
        }
        estimate.save()
        estimate.refresh_from_db()

        self.assertEqual(estimate.staff_total, Decimal("1020.00"))
        rows = estimate.per_meal_service_summary(apply_exchange=False)
        by_meal = {row["meal"]: row for row in rows}
        self.assertEqual(by_meal["Friday Night"]["wait_staff_count"], 1)
        self.assertEqual(by_meal["Shabbos Day"]["wait_staff_count"], 3)

    def test_per_meal_wait_staff_count_falls_back_to_default_waiters(self):
        estimate = self.estimate
        estimate.staff_hourly_rate = Decimal("50.00")
        estimate.staff_tip_per_waiter = Decimal("10.00")
        estimate.meal_plan = ["Friday Night"]
        estimate.meal_service_details = {
            "Friday Night": {
                "staff_hours": "2",
                "staff_tip_per_waiter": "10",
            }
        }
        estimate.save()
        estimate.refresh_from_db()

        rows = estimate.per_meal_service_summary(apply_exchange=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["wait_staff_count"], estimate.total_waiter_count())
        self.assertEqual(estimate.staff_total, Decimal("220.00"))

    def test_client_tipped_at_event_excludes_suggested_tip_from_staff_total(self):
        estimate = self.estimate
        estimate.staff_hourly_rate = Decimal("50.00")
        estimate.staff_tip_per_waiter = Decimal("20.00")
        estimate.staff_hours = Decimal("2.00")
        estimate.staff_count_override = 2
        estimate.client_tipped_at_event = True
        estimate.meal_service_details = {}
        estimate.save()
        estimate.refresh_from_db()

        self.assertEqual(estimate.staff_total, Decimal("200.00"))

    def test_client_tipped_at_event_excludes_per_meal_suggested_tip(self):
        estimate = self.estimate
        estimate.staff_hourly_rate = Decimal("50.00")
        estimate.staff_tip_per_waiter = Decimal("80.00")
        estimate.client_tipped_at_event = True
        estimate.meal_plan = ["Friday Night", "Shabbos Day"]
        estimate.meal_service_details = {
            "Friday Night": {
                "staff_hours": "2",
                "wait_staff_count": 1,
                "staff_tip_per_waiter": "80",
            },
            "Shabbos Day": {
                "staff_hours": "4",
                "wait_staff_count": 3,
                "staff_tip_per_waiter": "80",
            },
        }
        estimate.save()
        estimate.refresh_from_db()

        self.assertEqual(estimate.staff_total, Decimal("700.00"))
        rows = estimate.per_meal_service_summary(apply_exchange=False)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["staff_tip_total"], Decimal("0.00"))
            self.assertEqual(row["staff_tip_per_waiter"], Decimal("0.00"))

    def test_print_pdf_shows_client_tipped_note(self):
        estimate = self.estimate
        estimate.staff_hourly_rate = Decimal("50.00")
        estimate.staff_tip_per_waiter = Decimal("20.00")
        estimate.staff_count_override = 2
        estimate.client_tipped_at_event = True
        estimate.save()

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("admin:client_estimates_estimate_print", args=[estimate.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "- Client tipped at event.")

    def test_staff_summary_returns_qr_links(self):
        token = self._login_and_get_token("appstaff@example.com")
        response = self.client.get(
            reverse("xpenz_staff_summary", args=[self.estimate.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["roles"]), 3)
        self.assertIn("qr_image_url", payload["roles"][0])
        self.assertIn("punch_url", payload["roles"][0])

    def test_apply_staff_costs_creates_single_expense_entry(self):
        token = self._login_and_get_token("appstaff@example.com")
        now = timezone.now()
        entry1 = EstimateStaffTimeEntry.objects.create(
            estimate=self.estimate,
            role="KITCHEN",
            worker_first_name="Avi",
            hourly_rate=Decimal("50.00"),
            punched_in_at=now - timedelta(hours=2),
            punched_out_at=now - timedelta(hours=1),
            total_hours=Decimal("1.00"),
            total_cost=Decimal("50.00"),
        )
        entry2 = EstimateStaffTimeEntry.objects.create(
            estimate=self.estimate,
            role="WAIT",
            worker_first_name="Dan",
            hourly_rate=Decimal("40.00"),
            punched_in_at=now - timedelta(hours=3),
            punched_out_at=now - timedelta(hours=1),
            total_hours=Decimal("2.00"),
            total_cost=Decimal("80.00"),
        )

        response = self.client.post(
            reverse("xpenz_apply_staff_costs_to_expense", args=[self.estimate.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["applied_total"], "130.00")

        created_expense = EstimateExpenseEntry.objects.get(pk=payload["expense_entry_id"])
        self.assertEqual(created_expense.expense_amount, Decimal("130.00"))
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        self.assertTrue(entry1.applied_to_expenses)
        self.assertTrue(entry2.applied_to_expenses)

    def test_shopping_list_create_and_merge_duplicate_items(self):
        token = self._login_and_get_token("appstaff@example.com")
        create_response = self.client.post(
            reverse("xpenz_shopping_lists"),
            data=json.dumps(
                {
                    "caterer_id": self.caterer.id,
                    "title": "Friday Shopping",
                    "estimate_id": self.estimate.id,
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(create_response.status_code, 201)
        shopping_list_id = create_response.json()["shopping_list"]["id"]

        first_item = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list_id]),
            data=json.dumps(
                {
                    "item_name": "Mushrooms",
                    "item_type": "pack",
                    "item_unit": "Pieces",
                    "quantity": "2",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(first_item.status_code, 201)
        self.assertFalse(first_item.json()["merged"])

        second_item = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list_id]),
            data=json.dumps(
                {
                    "item_name": "mushrooms",
                    "item_type": "Pack",
                    "item_unit": "pieces",
                    "quantity": "3",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(second_item.status_code, 200)
        payload = second_item.json()
        self.assertTrue(payload["merged"])
        self.assertEqual(payload["item"]["quantity"], "5")
        self.assertEqual(payload["item"]["item_unit"], "Pieces")
        self.assertEqual(payload["item"]["collaboration_note"], "")

        detail_response = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list_id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["shopping_list"]["estimate_id"], self.estimate.id)
        self.assertEqual(len(detail_payload["items"]), 1)
        self.assertEqual(detail_payload["items"][0]["item_name"], "Mushrooms")

    def test_shopping_list_same_item_different_unit_does_not_merge(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Unit split",
            created_by=self.app_user,
        )
        first_item = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps(
                {
                    "item_name": "Chicken breast",
                    "item_type": "",
                    "item_unit": "Kg",
                    "quantity": "4",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(first_item.status_code, 201)

        second_item = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps(
                {
                    "item_name": "Chicken breast",
                    "item_type": "",
                    "item_unit": "Pieces",
                    "quantity": "8",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(second_item.status_code, 201)

        detail_response = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()["items"]), 2)

    def test_shopping_list_marks_combined_after_other_user_started_execution(self):
        owner_token = self._login_and_get_token("owner@example.com")
        app_token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Collab list",
            created_by=self.user,
        )
        pre_item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Salt",
            item_type="",
            item_unit="Kg",
            quantity=Decimal("1.00"),
            category="PANTRY",
            created_by=self.user,
        )
        active_item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Tomato",
            item_type="",
            item_unit="Kg",
            quantity=Decimal("2.00"),
            category="PRODUCE",
            created_by=self.user,
        )

        remove_response = self.client.post(
            reverse("xpenz_shopping_list_remove_item", args=[shopping_list.id, pre_item.id]),
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
        )
        self.assertEqual(remove_response.status_code, 200)

        add_response = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps(
                {
                    "item_name": "tomato",
                    "item_type": "",
                    "item_unit": "kg",
                    "quantity": "1",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {app_token}",
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["item"]["collaboration_note"], "combined")
        active_item.refresh_from_db()
        self.assertEqual(active_item.quantity, Decimal("3.00"))
        self.assertEqual(active_item.collaboration_note, "COMBINED")

    def test_shopping_list_marks_added_when_readding_executed_item_after_other_user_started(self):
        owner_token = self._login_and_get_token("owner@example.com")
        app_token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Added marker list",
            created_by=self.user,
        )
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Chicken breast",
            item_type="",
            item_unit="Kg",
            quantity=Decimal("4.00"),
            category="MEAT_POULTRY_FISH",
            created_by=self.user,
        )
        remove_response = self.client.post(
            reverse("xpenz_shopping_list_remove_item", args=[shopping_list.id, item.id]),
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
        )
        self.assertEqual(remove_response.status_code, 200)

        add_response = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps(
                {
                    "item_name": "Chicken breast",
                    "item_type": "",
                    "item_unit": "Kg",
                    "quantity": "2",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {app_token}",
        )
        self.assertEqual(add_response.status_code, 201)
        payload = add_response.json()
        self.assertEqual(payload["item"]["collaboration_note"], "added")

    def test_shopping_list_remove_item(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Market run",
            created_by=self.app_user,
        )
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Chicken breast",
            item_type="kg",
            quantity=Decimal("4.00"),
            category="MEAT_POULTRY_FISH",
            created_by=self.app_user,
        )

        remove_response = self.client.post(
            reverse("xpenz_shopping_list_remove_item", args=[shopping_list.id, item.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(remove_response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_completed)
        self.assertEqual(item.completed_by, self.app_user)
        self.assertIsNotNone(item.completed_at)
        shopping_list.refresh_from_db()
        self.assertEqual(shopping_list.execution_started_by, self.app_user)
        self.assertIsNotNone(shopping_list.execution_started_at)

        detail_response = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["items"], [])

        list_response = self.client.get(
            reverse("xpenz_shopping_lists"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(list_response.status_code, 200)
        row = next(
            (entry for entry in list_response.json()["lists"] if entry["id"] == shopping_list.id),
            None,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["item_count"], 0)

    def test_shopping_list_delete_hides_list_and_keeps_items_for_catalog(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Delete me",
            created_by=self.app_user,
        )
        item = ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Tomato",
            quantity=Decimal("2.00"),
            category="PRODUCE",
            created_by=self.app_user,
        )

        delete_response = self.client.post(
            reverse("xpenz_shopping_list_delete", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["ok"])
        shopping_list.refresh_from_db()
        self.assertIsNotNone(shopping_list.deleted_at)
        self.assertTrue(ShoppingListItem.objects.filter(id=item.id).exists())

        detail_response = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(detail_response.status_code, 404)

        list_response = self.client.get(
            reverse("xpenz_shopping_lists"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertFalse(
            any(row["id"] == shopping_list.id for row in list_response.json()["lists"])
        )

        catalog_response = self.client.get(
            reverse("xpenz_shopping_catalog"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(catalog_response.status_code, 200)
        self.assertTrue(
            any(
                row["item_name"].lower() == "tomato"
                for row in catalog_response.json()["items"]
            )
        )

    def test_shopping_list_category_sorting(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Sorted list",
            created_by=self.app_user,
        )
        # Add out of order; response should return Produce before Meat before Pantry.
        self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps({"item_name": "salt", "quantity": "1"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps({"item_name": "chicken breast", "quantity": "2"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps({"item_name": "tomato", "quantity": "3"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        detail_response = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(detail_response.status_code, 200)
        categories = [row["category"] for row in detail_response.json()["items"]]
        self.assertEqual(categories[:3], ["PRODUCE", "MEAT_POULTRY_FISH", "PANTRY"])

    def test_shopping_list_changes_returns_unchanged_when_cursor_matches(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Changes list",
            created_by=self.app_user,
        )
        snapshot = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(snapshot.status_code, 200)
        cursor = snapshot.json()["shopping_list"]["updated_at"]

        response = self.client.get(
            reverse("xpenz_shopping_list_changes", args=[shopping_list.id]),
            data={"since": cursor, "timeout": "0"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["changed"])
        self.assertEqual(payload["items"], [])

    def test_shopping_list_changes_returns_items_after_update(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Changes update list",
            created_by=self.app_user,
        )
        snapshot = self.client.get(
            reverse("xpenz_shopping_list_detail", args=[shopping_list.id]),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(snapshot.status_code, 200)
        cursor = snapshot.json()["shopping_list"]["updated_at"]

        create_item = self.client.post(
            reverse("xpenz_shopping_list_items", args=[shopping_list.id]),
            data=json.dumps(
                {"item_name": "Tomato", "item_unit": "Kg", "quantity": "2"}
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(create_item.status_code, 201)

        changes_response = self.client.get(
            reverse("xpenz_shopping_list_changes", args=[shopping_list.id]),
            data={"since": cursor, "timeout": "0"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(changes_response.status_code, 200)
        payload = changes_response.json()
        self.assertTrue(payload["changed"])
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["item_name"], "Tomato")

    def test_shopping_list_create_denied_for_other_caterer(self):
        token = self._login_and_get_token("appstaff@example.com")
        response = self.client.post(
            reverse("xpenz_shopping_lists"),
            data=json.dumps({"caterer_id": self.other_caterer.id, "title": "No access"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 403)

    def test_shopping_catalog_groups_items_and_remembers_type_options(self):
        token = self._login_and_get_token("appstaff@example.com")
        shopping_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Memory list",
            created_by=self.app_user,
        )
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="Apples",
            item_type="Green",
            quantity=Decimal("2.00"),
            category="PRODUCE",
            is_completed=True,
            created_by=self.app_user,
        )
        ShoppingListItem.objects.create(
            shopping_list=shopping_list,
            item_name="apples",
            item_type="Red",
            item_unit="Kg",
            quantity=Decimal("3.00"),
            category="PRODUCE",
            created_by=self.app_user,
        )

        response = self.client.get(
            reverse("xpenz_shopping_catalog"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        apples = next(
            (row for row in payload["items"] if row["item_name"].lower() == "apples"),
            None,
        )
        self.assertIsNotNone(apples)
        self.assertEqual(apples["category"], "PRODUCE")
        self.assertEqual(apples["usage_count"], 2)
        self.assertEqual(apples["type_options"], ["Green", "Red"])
        self.assertEqual(apples["unit_options"], ["Kg", "Pieces", "Cans"])
        self.assertEqual(apples["last_used_unit"], "Kg")

    def test_admin_saved_item_category_override_is_used_for_future_auto_sort(self):
        source_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Source list",
            created_by=self.user,
        )
        ShoppingListItem.objects.create(
            shopping_list=source_list,
            item_name="Lemon",
            quantity=Decimal("1.00"),
            category="PRODUCE",
            created_by=self.user,
        )

        self.client.force_login(self.user)
        admin_response = self.client.post(
            reverse("admin:shopping_list_tool_shoppinglistbulkimport_bulk_import"),
            data={
                "action": "set_category",
                "caterer": self.caterer.id,
                "item_name": "Lemon",
                "category": "PANTRY",
            },
            follow=False,
        )
        self.assertEqual(admin_response.status_code, 302)
        self.assertTrue(
            ShoppingListItem.objects.filter(
                shopping_list__caterer=self.caterer,
                item_name__iexact="Lemon",
                category="PANTRY",
            ).exists()
        )

        token = self._login_and_get_token("appstaff@example.com")
        target_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Target list",
            created_by=self.app_user,
        )
        add_response = self.client.post(
            reverse("xpenz_shopping_list_items", args=[target_list.id]),
            data=json.dumps({"item_name": "Lemon", "quantity": "2"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(add_response.json()["item"]["category"], "PANTRY")

    def test_admin_bulk_saved_item_category_override_updates_multiple_items(self):
        source_list = ShoppingList.objects.create(
            caterer=self.caterer,
            title="Bulk category source",
            created_by=self.user,
        )
        ShoppingListItem.objects.create(
            shopping_list=source_list,
            item_name="Lemon",
            quantity=Decimal("1.00"),
            category="PRODUCE",
            created_by=self.user,
        )
        ShoppingListItem.objects.create(
            shopping_list=source_list,
            item_name="Chicken Breast",
            quantity=Decimal("2.00"),
            category="MEAT_POULTRY_FISH",
            created_by=self.user,
        )

        self.client.force_login(self.user)
        admin_response = self.client.post(
            reverse("admin:shopping_list_tool_shoppinglistbulkimport_bulk_import"),
            data={
                "action": "set_category_bulk",
                "caterer": self.caterer.id,
                "row_count": "2",
                "item_name_0": "Lemon",
                "category_0": "PANTRY",
                "item_name_1": "Chicken Breast",
                "category_1": "PANTRY",
            },
            follow=False,
        )
        self.assertEqual(admin_response.status_code, 302)
        self.assertTrue(
            ShoppingListItem.objects.filter(
                shopping_list__caterer=self.caterer,
                item_name__iexact="Lemon",
                category="PANTRY",
            ).exists()
        )
        self.assertTrue(
            ShoppingListItem.objects.filter(
                shopping_list__caterer=self.caterer,
                item_name__iexact="Chicken Breast",
                category="PANTRY",
            ).exists()
        )

    def test_admin_can_create_app_user_from_global_permissions_tab(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("admin:app_users_appuser_create_app_user"),
            data={
                "caterer": self.caterer.id,
                "first_name": "New",
                "email": "newapp@example.com",
                "password": "temp-pass-123",
                "can_add_expenses": "on",
                "can_view_job_billing": "",
                "can_manage_staff": "on",
            },
        )
        self.assertEqual(response.status_code, 302)

        user_model = get_user_model()
        created_user = user_model.objects.get(username="newapp@example.com")
        access = CatererUserAccess.objects.get(caterer=self.caterer, user=created_user)
        self.assertTrue(access.can_access_mobile_app)
        self.assertTrue(access.can_add_expenses)
        self.assertFalse(access.can_view_job_billing)
        self.assertTrue(access.can_manage_staff)

    def test_admin_can_edit_unapplied_staff_record_before_expense_apply(self):
        now = timezone.now().replace(microsecond=0)
        entry = EstimateStaffTimeEntry.objects.create(
            estimate=self.estimate,
            role="WAIT",
            worker_first_name="Joe",
            hourly_rate=Decimal("40.00"),
            punched_in_at=now - timedelta(hours=2),
            punched_out_at=now - timedelta(hours=1),
            total_hours=Decimal("1.00"),
            total_cost=Decimal("40.00"),
        )

        self.client.force_login(self.user)
        punched_in = now - timedelta(hours=2)
        punched_out = now - timedelta(minutes=30)
        response = self.client.post(
            reverse("admin:client_estimates_estimatestafftimeentry_change", args=[entry.id]),
            data={
                "role": "WAIT",
                "worker_first_name": "Joe Edited",
                "hourly_rate": "45.00",
                "punched_in_at_0": punched_in.strftime("%Y-%m-%d"),
                "punched_in_at_1": punched_in.strftime("%H:%M:%S"),
                "punched_out_at_0": punched_out.strftime("%Y-%m-%d"),
                "punched_out_at_1": punched_out.strftime("%H:%M:%S"),
                "_save": "Save",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)

        entry.refresh_from_db()
        self.assertEqual(entry.worker_first_name, "Joe Edited")
        self.assertEqual(entry.hourly_rate, Decimal("45.00"))
        self.assertEqual(entry.total_hours, Decimal("1.50"))
        self.assertEqual(entry.total_cost, Decimal("67.50"))

    def test_admin_can_delete_expense_entry_for_owned_estimate(self):
        entry = EstimateExpenseEntry.objects.create(
            estimate=self.estimate,
            created_by=self.user,
            receipt_image=SimpleUploadedFile(
                "receipt-delete.jpg",
                b"fake-jpg-content",
                content_type="image/jpeg",
            ),
            expense_text="Delete me",
            expense_amount=Decimal("9.99"),
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("admin:client_estimates_estimate_expense_delete", args=[self.estimate.id, entry.id]),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(EstimateExpenseEntry.objects.filter(pk=entry.pk).exists())

    def test_admin_cannot_delete_expense_entry_for_other_owner(self):
        entry = EstimateExpenseEntry.objects.create(
            estimate=self.estimate,
            created_by=self.user,
            receipt_image=SimpleUploadedFile(
                "receipt-denied.jpg",
                b"fake-jpg-content",
                content_type="image/jpeg",
            ),
            expense_text="Should stay",
            expense_amount=Decimal("11.00"),
        )
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("admin:client_estimates_estimate_expense_delete", args=[self.estimate.id, entry.id]),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(EstimateExpenseEntry.objects.filter(pk=entry.pk).exists())

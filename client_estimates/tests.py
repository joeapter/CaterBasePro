from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import CatererAccount, Estimate, EstimateExpenseEntry


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

    def _login_and_get_token(self):
        response = self.client.post(
            reverse("xpenz_mobile_login"),
            data=json.dumps({"username": "owner@example.com", "password": "secret123"}),
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

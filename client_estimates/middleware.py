from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import CatererAccount


class TrialExpiryMiddleware:
    """
    Block expired trial users (non-superusers) and redirect them to the trial expiry page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response:
            return response
        return self.get_response(request)

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None

        # Paths to ignore to avoid loops
        ignored = {
            reverse("trial_expired"),
            reverse("marketing_home"),
            reverse("start_trial"),
            reverse("admin:login"),
            reverse("admin:logout"),
        }
        if any(request.path.startswith(path) for path in ignored):
            return None

        caterer = CatererAccount.objects.filter(owner=user).first()
        if not caterer or not caterer.trial_expires_at:
            return None

        if timezone.now() > caterer.trial_expires_at:
            return redirect("trial_expired")

        return None

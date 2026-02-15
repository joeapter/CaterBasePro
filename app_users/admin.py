from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse

from client_estimates.models import CatererAccount, CatererUserAccess

from .models import AppUser


class AppUserCreateForm(forms.Form):
    caterer = forms.ModelChoiceField(
        queryset=CatererAccount.objects.none(),
        label="Caterer",
    )
    first_name = forms.CharField(
        max_length=150,
        label="First name",
    )
    email = forms.EmailField(
        label="Login email",
        help_text="This email is used as the username for mobile app login.",
    )
    password = forms.CharField(
        required=False,
        label="Password (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to auto-generate a temporary password.",
    )
    can_add_expenses = forms.BooleanField(
        required=False,
        initial=True,
        label="Can add expenses",
    )
    can_view_job_billing = forms.BooleanField(
        required=False,
        initial=False,
        label="Can view billing totals",
    )
    can_manage_staff = forms.BooleanField(
        required=False,
        initial=False,
        label="Can manage staff tab",
    )


@admin.register(AppUser)
class AppUserAdmin(admin.ModelAdmin):
    change_list_template = "admin/app_users/app_user_changelist.html"
    list_display = (
        "caterer",
        "user",
        "is_active",
        "can_access_mobile_app",
        "can_add_expenses",
        "can_view_job_billing",
        "can_manage_staff",
    )
    list_filter = (
        "is_active",
        "can_access_mobile_app",
        "can_add_expenses",
        "can_view_job_billing",
        "can_manage_staff",
        "caterer",
    )
    search_fields = ("user__username", "user__email", "caterer__name")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "create-app-user/",
                self.admin_site.admin_view(self.create_app_user),
                name="app_users_appuser_create_app_user",
            ),
        ]
        return custom + urls

    def _allowed_caterers(self, request):
        qs = CatererAccount.objects.all()
        if request.user.is_superuser:
            return qs
        return qs.filter(owner=request.user)

    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        extra["create_app_user_url"] = reverse("admin:app_users_appuser_create_app_user")
        return super().changelist_view(request, extra_context=extra)

    def create_app_user(self, request):
        allowed_caterers = self._allowed_caterers(request).order_by("name")
        if not request.user.is_superuser and not allowed_caterers.exists():
            raise PermissionDenied("No caterer account is available for this user.")

        user_model = get_user_model()
        if request.method == "POST":
            form = AppUserCreateForm(request.POST)
        else:
            form = AppUserCreateForm()
        form.fields["caterer"].queryset = allowed_caterers
        if not request.user.is_superuser and allowed_caterers.count() == 1:
            form.fields["caterer"].initial = allowed_caterers.first()

        if request.method == "POST" and form.is_valid():
            caterer = form.cleaned_data["caterer"]
            if not request.user.is_superuser and caterer.owner_id != request.user.id:
                raise PermissionDenied("You do not have access to this caterer.")

            email = form.cleaned_data["email"].strip().lower()
            username = email
            existing = user_model.objects.filter(username__iexact=username).first()
            if not existing:
                existing = user_model.objects.filter(email__iexact=email).first()
            if existing:
                form.add_error("email", "A user with this email/username already exists.")
            else:
                password = (form.cleaned_data["password"] or "").strip()
                generated = False
                if not password:
                    password = user_model.objects.make_random_password(length=10)
                    generated = True
                user = user_model.objects.create_user(
                    username=username,
                    email=email,
                    first_name=form.cleaned_data["first_name"].strip(),
                    password=password,
                    is_active=True,
                    is_staff=False,
                )
                CatererUserAccess.objects.update_or_create(
                    caterer=caterer,
                    user=user,
                    defaults={
                        "is_active": True,
                        "can_access_mobile_app": True,
                        "can_add_expenses": bool(form.cleaned_data["can_add_expenses"]),
                        "can_view_job_billing": bool(form.cleaned_data["can_view_job_billing"]),
                        "can_manage_staff": bool(form.cleaned_data["can_manage_staff"]),
                    },
                )
                msg = f"App user {email} created."
                if generated:
                    msg += f" Temporary password: {password}"
                self.message_user(request, msg, level=messages.SUCCESS)
                list_url = reverse("admin:app_users_appuser_changelist")
                return redirect(f"{list_url}?caterer__id__exact={caterer.id}")

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Create app user",
            "form": form,
            "back_url": reverse("admin:app_users_appuser_changelist"),
        }
        return render(request, "admin/app_users/create_app_user.html", context)

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("caterer", "user")
        if request.user.is_superuser:
            return qs
        return qs.filter(caterer__owner=request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and "caterer" in form.base_fields:
            form.base_fields["caterer"].queryset = CatererAccount.objects.filter(
                owner=request.user
            )
        return form

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return CatererAccount.objects.filter(owner=request.user).exists()
        return obj.caterer.owner == request.user

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return CatererAccount.objects.filter(owner=request.user).exists()
        return obj.caterer.owner == request.user

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return CatererAccount.objects.filter(owner=request.user).exists()
        return obj.caterer.owner == request.user

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return CatererAccount.objects.filter(owner=request.user).exists()

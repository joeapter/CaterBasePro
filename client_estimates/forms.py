from django import forms

from .models import ClientInquiry


class ClientInquiryForm(forms.ModelForm):
    class Meta:
        model = ClientInquiry
        fields = [
            "contact_name",
            "company_name",
            "email",
            "phone",
            "preferred_contact_method",
            "event_type",
            "event_date",
            "notes",
        ]
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

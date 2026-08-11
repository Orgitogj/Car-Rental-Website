from django import forms
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import Car, Company, ContactMessage, Extra

TEXT = {"class": "field__input"}
AREA = {"class": "field__input", "rows": 4}
SELECT = {"class": "field__input field__input--select"}


class MultipleFileInput(forms.ClearableFileInput):

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return clean_one(data, initial)


class StyledModelForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{existing} field__checkbox".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{existing} field__input field__input--select".strip()
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs["class"] = f"{existing} field__file".strip()
            else:
                widget.attrs["class"] = f"{existing} field__input".strip()

            if field.required:
                widget.attrs["aria-required"] = "true"

    def add_error_classes(self):
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["aria-invalid"] = "true"


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


class CarForm(StyledModelForm):
    images = MultipleFileField(
        required=False,
        label=_("Photos"),
        help_text=_("JPEG, PNG or WebP. The first photo becomes the cover."),
    )

    class Meta:
        model = Car
        fields = (
            "name",
            "brand",
            "car_type",
            "description",
            "price_per_day",
            "year",
            "seats",
            "doors",
            "bags",
            "power",
            "engine_size",
            "fuel",
            "gear",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs=AREA),
            "price_per_day": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "year": forms.NumberInput(attrs={"min": "1950", "max": "2100"}),
            "seats": forms.NumberInput(attrs={"min": "1", "max": "20"}),
            "doors": forms.NumberInput(attrs={"min": "1", "max": "8"}),
            "bags": forms.NumberInput(attrs={"min": "0", "max": "12"}),
            "power": forms.NumberInput(attrs={"min": "1"}),
        }
        labels = {
            "name": _("Model"),
            "car_type": _("Category"),
            "price_per_day": _("Price per day"),
            "power": _("Power (HP)"),
            "is_active": _("Listed on the public site"),
        }

    def clean_price_per_day(self):
        price = self.cleaned_data["price_per_day"]
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price cannot be negative."))
        return price

    def clean_year(self):
        year = self.cleaned_data["year"]
        if year and (year < 1950 or year > 2100):
            raise forms.ValidationError(_("Please enter a realistic year."))
        return year


class ExtraForm(StyledModelForm):
    class Meta:
        model = Extra
        fields = ("name", "description", "price_per_day", "is_active", "sort_order")
        widgets = {
            "price_per_day": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


# ---------------------------------------------------------------------------
# Companies (super admin)
# ---------------------------------------------------------------------------


class CompanyForm(StyledModelForm):
    """Edit an existing company."""

    logo = forms.ImageField(
        required=False,
        label=_("Company logo"),
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = Company
        fields = (
            "name",
            "description",
            "email",
            "phone",
            "city",
            "address",
            "website",
            "status",
        )
        widgets = {"description": forms.Textarea(attrs=AREA)}


class CompanyCreateForm(CompanyForm):

    owner_full_name = forms.CharField(max_length=100, label=_("Owner full name"))
    owner_email = forms.EmailField(label=_("Owner email (used to sign in)"))
    owner_password = forms.CharField(
        label=_("Owner password"), widget=forms.PasswordInput(render_value=False)
    )

    field_order = [
        "name",
        "email",
        "phone",
        "city",
        "address",
        "website",
        "description",
        "status",
        "logo",
        "owner_full_name",
        "owner_email",
        "owner_password",
    ]

    def clean_owner_email(self):
        email = self.cleaned_data["owner_email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(_("A user with this email already exists."))
        return email

    def clean_owner_password(self):
        from django.contrib.auth.password_validation import validate_password

        password = self.cleaned_data["owner_password"]
        validate_password(password)
        return password


# ---------------------------------------------------------------------------
# Public site
# ---------------------------------------------------------------------------


class ContactForm(StyledModelForm):
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
        label="",
    )

    class Meta:
        model = ContactMessage
        fields = ("full_name", "email", "subject", "message")
        widgets = {"message": forms.Textarea(attrs=AREA)}
        labels = {
            "full_name": _("Your name"),
            "email": _("Email address"),
            "subject": _("Subject"),
            "message": _("How can we help?"),
        }

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError(_("Submission rejected."))
        return ""

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message) < 10:
            raise forms.ValidationError(
                _("Please give us a little more detail (at least 10 characters).")
            )
        return message


class BookingLookupForm(forms.Form):
    reference = forms.CharField(
        max_length=20,
        label=_("Booking reference"),
        widget=forms.TextInput(
            attrs={"class": "field__input", "placeholder": "CR-XXXXXXXX"}
        ),
    )
    full_name = forms.CharField(
        max_length=100,
        label=_("Full name on the booking"),
        widget=forms.TextInput(attrs={"class": "field__input"}),
    )

    def clean_reference(self):
        return self.cleaned_data["reference"].strip().upper()


class CompanyProfileForm(StyledModelForm):

    logo = forms.ImageField(
        required=False,
        label=_("Company logo"),
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = Company
        fields = ("name", "description", "email", "phone", "city", "address", "website")
        widgets = {"description": forms.Textarea(attrs=AREA)}

import re
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from ..forms import MultipleFileInput

PHONE_RE = re.compile(r"^[\d\s+\-()]+$")
DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class LoginForm(forms.Form):
    username = forms.CharField(
        label=_("Email or username"),
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": _("you@example.com or your username"),
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={"class": "field__input", "autocomplete": "current-password"}
        ),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip()


class RegisterForm(forms.Form):
    full_name = forms.CharField(
        label=_("Full name"),
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "field__input", "autocomplete": "name", "autofocus": True}
        ),
    )
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(
            attrs={"class": "field__input", "autocomplete": "email"}
        ),
    )
    phone = forms.CharField(
        label=_("Phone number"),
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "field__input", "autocomplete": "tel"}
        ),
    )
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={"class": "field__input", "autocomplete": "new-password"}
        ),
        help_text=_("At least 8 characters, not entirely numeric."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(
            attrs={"class": "field__input", "autocomplete": "new-password"}
        ),
    )

    def clean_full_name(self):
        name = self.cleaned_data["full_name"].strip()
        if len(name) < 3:
            raise forms.ValidationError(_("Please enter your full name."))
        return name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(
                _("An account with this email already exists.")
            )
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError(_("Please enter a valid phone number."))
        if len(re.sub(r"\D", "", phone)) < 8:
            raise forms.ValidationError(
                _("Please enter a phone number with at least 8 digits.")
            )
        return phone

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("The two passwords do not match."))
        return cleaned


class CompanyRegistrationForm(forms.Form):
    
    STEP_ONE_FIELDS = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "password1",
        "password2",
    )
    first_name = forms.CharField(
        label=_("First Name"),
        max_length=60,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "given-name",
                "autofocus": True,
                "placeholder": _("Enter your first name"),
            }
        ),
    )
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=60,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "family-name",
                "placeholder": _("Enter your last name"),
            }
        ),
    )
    email = forms.EmailField(
        label=_("Account Email"),
        widget=forms.EmailInput(
            attrs={
                "class": "field__input",
                "autocomplete": "email",
                "placeholder": "name@example.com",
            }
        ),
        help_text=_("You will sign in to the company panel with this address."),
    )
    phone = forms.CharField(
        label=_("Phone Number"),
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "tel",
                "placeholder": "+355 69 000 0000",
            }
        ),
    )
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={"class": "field__input", "autocomplete": "new-password"}
        ),
        help_text=_("At least 8 characters, not entirely numeric."),
    )
    password2 = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "field__input",
                "autocomplete": "new-password",
                "placeholder": _("Confirm password"),
            }
        ),
    )
    business_name = forms.CharField(
        label=_("Business Name"),
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "organization",
                "placeholder": _("Your company's trading name"),
            }
        ),
    )
    business_email = forms.EmailField(
        label=_("Business Email"),
        widget=forms.EmailInput(
            attrs={"class": "field__input", "placeholder": "contact@company.com"}
        ),
    )
    legal_name = forms.CharField(
        label=_("Legal Business Name"),
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "field__input", "placeholder": _("Registered legal name")}
        ),
    )
    city = forms.CharField(
        label=_("City"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "address-level2",
                "placeholder": _("City where the business operates"),
            }
        ),
    )
    address = forms.CharField(
        label=_("Address"),
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field__input",
                "autocomplete": "street-address",
                "placeholder": _("Street address or office location"),
            }
        ),
    )
    state = forms.CharField(
        label=_("State"),
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "field__input", "placeholder": _("State of registration")}
        ),
    )
    tin = forms.CharField(
        label=_("TIN"),
        max_length=40,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "field__input", "placeholder": _("Tax Identification Number")}
        ),
    )
    tax_number = forms.CharField(
        label=_("Tax Number"),
        max_length=40,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "field__input", "placeholder": _("Tax Identification Number")}
        ),
    )
    documents = forms.FileField(
        label=_("Business Documents"),
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "field__file", "accept": ".pdf,.jpg,.jpeg,.png"}
        ),
    )
    accept_terms = forms.BooleanField(
        label=_("I accept the terms and privacy policy."),
        error_messages={
            "required": _("Please accept the terms to create your account.")
        },
        widget=forms.CheckboxInput(attrs={"class": "field__checkbox"}),
    )

    # -- validation ----------------------------------------------------------

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError(_("Please enter a valid phone number."))
        if len(re.sub(r"\D", "", phone)) < 8:
            raise forms.ValidationError(
                _("Please enter a phone number with at least 8 digits.")
            )
        return phone

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean_business_name(self):
        name = self.cleaned_data["business_name"].strip()
        if len(name) < 2:
            raise forms.ValidationError(_("Please enter your business name."))
        return name

    def clean_business_email(self):
        return self.cleaned_data["business_email"].strip().lower()

    def clean_documents(self):
        """`documents` is rendered as a multi-file input, so read the raw list."""
        uploads = self.files.getlist("documents") if self.files else []
        limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        limit_mb = limit // (1024 * 1024)

        for upload in uploads:
            if upload.size > limit:
                raise forms.ValidationError(
                    _("%(file)s is larger than the %(limit)sMB limit.")
                    % {"file": upload.name, "limit": limit_mb}
                )
            if (upload.content_type or "").lower() not in DOCUMENT_TYPES:
                raise forms.ValidationError(
                    _("%(file)s must be a PDF, JPG or PNG file.")
                    % {"file": upload.name}
                )
        return uploads

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("The two passwords do not match."))
        return cleaned

    # -- wizard helpers ------------------------------------------------------

    @property
    def full_name(self):
        first = self.cleaned_data.get("first_name", "")
        last = self.cleaned_data.get("last_name", "")
        return f"{first} {last}".strip()

    @property
    def first_invalid_step(self):
        if any(name in self.errors for name in self.STEP_ONE_FIELDS):
            return 1
        return 2

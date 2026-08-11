from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from ..access import SESSION_KEY, own_company
from ..services import companies as company_service
from ..services import contracts as contract_service
from .forms import CompanyRegistrationForm, LoginForm, RegisterForm
from .models import Profile


def _destination_for(user):
    if user.is_superuser:
        return reverse("superadmin_dashboard")

    company = own_company(user)
    if company is not None:
        if contract_service.requires_signature(company):
            return reverse("company_contract")
        return reverse("company_dashboard")

    return reverse("home")


def _safe_next(request, fallback):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


@sensitive_post_parameters("password")
@never_cache
def login_view(request, portal=False):
    template = "auth/portal_login.html" if portal else "auth/login.html"

    if request.user.is_authenticated:
        return redirect(_destination_for(request.user))

    form = LoginForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )

            if user is None:
                messages.error(request, _("Incorrect email, username or password."))
            elif not user.is_active:
                messages.error(
                    request, _("This account has been deactivated. Contact support.")
                )
            else:
                login(request, user)
                request.session.pop(SESSION_KEY, None)

                if portal and not (user.is_superuser or own_company(user)):
                    logout(request)
                    messages.error(
                        request,
                        _("This portal is for rental companies and platform staff."),
                    )
                    return redirect("portal_login")

                return redirect(_safe_next(request, _destination_for(user)))
        else:
            messages.error(request, _("Please check the details you entered."))

    return render(request, template, {"form": form, "portal": portal})


def portal_login(request):
    return login_view(request, portal=True)


@sensitive_post_parameters("password1", "password2")
@never_cache
def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data

        with transaction.atomic():
            user = User.objects.create_user(
                username=data["email"],
                email=data["email"],
                password=data["password1"],
            )
            user.first_name = data["full_name"][:150]
            user.save(update_fields=["first_name"])
            Profile.objects.create(user=user, phone=data["phone"])

        login(request, user)
        messages.success(request, _("Welcome aboard, %(name)s.") % {"name": user.first_name})
        return redirect("home")

    return render(request, "auth/signup.html", {"form": form})


@sensitive_post_parameters("password1", "password2")
@never_cache
def company_register(request):
    if request.user.is_authenticated:
        return redirect(_destination_for(request.user))

    form = CompanyRegistrationForm(
        request.POST or None, request.FILES or None
    )
    step = 1

    if request.method == "POST":
        if form.is_valid():
            company, contract = company_service.register_company(
                form, request=request
            )
            login(request, company.owner)
            request.session.pop(SESSION_KEY, None)

            messages.success(
                request,
                _("Welcome, %(name)s. One step left: sign your platform contract.")
                % {"name": company.name},
            )
            return redirect("company_contract")

        step = form.first_invalid_step
        messages.error(request, _("Please check the details you entered."))

    return render(
        request,
        "auth/company_register.html",
        {"form": form, "step": step},
    )


def logout_view(request):
    if request.method == "POST" or request.GET.get("confirm") == "1":
        logout(request)
        messages.success(request, _("You have been signed out."))
    return redirect("home")


def portal_logout(request):
    logout(request)
    return redirect("portal_login")

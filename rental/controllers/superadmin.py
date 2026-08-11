from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from ..access import superadmin_required
from ..forms import CompanyCreateForm, CompanyForm
from ..models import AuditLog, Booking, Car, Company, ContactMessage, Customer
from ..selectors import metrics
from ..services import audit as audit_service
from ..services import companies as company_service
from ..utils import paginate, querystring

COMPANY_SORTS = {
    "name": "name",
    "-name": "-name",
    "created": "created_at",
    "-created": "-created_at",
    "revenue": "revenue",
    "-revenue": "-revenue",
    "fleet": "fleet_count",
    "-fleet": "-fleet_count",
    "bookings": "booking_count",
    "-bookings": "-booking_count",
}


@superadmin_required
def dashboard(request):
    period = 30
    return render(
        request,
        "superadmin/dashboard.html",
        {
            "m": metrics.platform_dashboard(days=period),
            "revenue_series": metrics.platform_revenue_series(days=period),
            "top_companies": metrics.top_companies(limit=5, days=period),
            "recent_activity": AuditLog.objects.with_actor()[:8],
            "recent_bookings": Booking.objects.with_display_data()[:6],
            "active_nav": "dashboard",
        },
    )


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@superadmin_required
def companies(request):
    qs = metrics.company_table_queryset()

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(city__icontains=query)
            | Q(owner__username__icontains=query)
        )

    status = request.GET.get("status")
    if status in Company.Status.values:
        qs = qs.filter(status=status)

    created_from = request.GET.get("from")
    created_to = request.GET.get("to")
    if created_from:
        qs = qs.filter(created_at__date__gte=created_from)
    if created_to:
        qs = qs.filter(created_at__date__lte=created_to)

    sort = request.GET.get("sort", "-created")
    qs = qs.order_by(COMPANY_SORTS.get(sort, "-created_at"))

    counts = Company.objects.aggregate(
        all=Count("id"),
        active=Count("id", filter=Q(status=Company.Status.ACTIVE)),
        pending=Count("id", filter=Q(status=Company.Status.PENDING)),
        suspended=Count("id", filter=Q(status=Company.Status.SUSPENDED)),
    )

    page = paginate(request, qs, per_page=15)

    return render(
        request,
        "superadmin/companies.html",
        {
            "page_obj": page,
            "companies": page.object_list,
            "counts": counts,
            "query": query,
            "status": status or "",
            "created_from": created_from or "",
            "created_to": created_to or "",
            "sort": sort,
            "statuses": Company.Status.choices,
            "querystring": querystring(request, page=None),
            "active_nav": "companies",
        },
    )


@superadmin_required
def company_create(request):
    form = CompanyCreateForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        company = company_service.create_company(form, request=request)
        messages.success(
            request, _("Company '%(name)s' created.") % {"name": company.name}
        )
        return redirect("superadmin_companies")

    form.add_error_classes()
    return render(
        request,
        "superadmin/company_form.html",
        {"form": form, "mode": "create", "active_nav": "companies"},
    )


@superadmin_required
def company_edit(request, company_id):
    """A company's own profile, read-only.

    The profile belongs to the company and is edited by its owner at
    `/portal/settings/`. The platform administrator may read it here, but not
    change it — the same rule the read-only drill-in applies, enforced the same
    way. Platform-level actions (status, deletion) live in their own views and
    are unaffected.
    """
    company = get_object_or_404(Company, pk=company_id)

    if request.method == "POST":
        audit_service.record_denied_action(request, description="company_edit")
        raise PermissionDenied(
            f"{company.name}'s profile is maintained by the company itself "
            "and cannot be edited from the platform console."
        )

    form = CompanyForm(instance=company)
    form.add_error_classes()
    return render(
        request,
        "superadmin/company_form.html",
        {
            "form": form,
            "company": company,
            "mode": "edit",
            "active_nav": "companies",
        },
    )


@superadmin_required
def company_delete(request, company_id):
    company = get_object_or_404(Company, pk=company_id)

    if request.method == "POST":
        name = company.name
        company_service.delete_company(company, request=request)
        messages.success(request, _("Company '%(name)s' deleted.") % {"name": name})
        return redirect("superadmin_companies")

    return render(
        request,
        "superadmin/company_confirm_delete.html",
        {
            "company": company,
            "fleet_count": company.cars.count(),
            "booking_count": company.bookings.count(),
            "active_nav": "companies",
        },
    )


@superadmin_required
@require_POST
def company_status(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    company_service.set_company_status(
        company, request.POST.get("status"), request=request
    )
    messages.success(
        request,
        _("%(name)s is now %(status)s.")
        % {"name": company.name, "status": company.get_status_display().lower()},
    )
    return redirect(request.POST.get("next") or "superadmin_companies")


@superadmin_required
def company_enter(request, company_id):
    """Open a company's own console, read-only."""
    company = get_object_or_404(Company, pk=company_id)
    company_service.enter_company_view(request, company)
    return redirect("company_dashboard")


@superadmin_required
def company_exit(request):
    company_service.exit_company_view(request)
    return redirect("superadmin_companies")


# ---------------------------------------------------------------------------
# Fleet / bookings overview 
# ---------------------------------------------------------------------------


@superadmin_required
def fleet_overview(request):
    qs = (
        Car.objects.select_related("company")
        .prefetch_related("images")
        .annotate(booking_count=Count("bookings", distinct=True))
    )

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(brand__icontains=query)
            | Q(company__name__icontains=query)
        )

    company_id = request.GET.get("company")
    if company_id:
        qs = qs.filter(company_id=company_id)

    page = paginate(request, qs.order_by("company__name", "brand", "name"), per_page=20)

    return render(
        request,
        "superadmin/fleet.html",
        {
            "page_obj": page,
            "cars": page.object_list,
            "companies": Company.objects.all(),
            "query": query,
            "company_id": company_id or "",
            "querystring": querystring(request, page=None),
            "active_nav": "fleet",
        },
    )


@superadmin_required
def bookings_overview(request):
    qs = Booking.objects.with_display_data()

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(reference__icontains=query)
            | Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(company__name__icontains=query)
        )

    status = request.GET.get("status")
    if status in Booking.Status.values:
        qs = qs.filter(status=status)

    company_id = request.GET.get("company")
    if company_id:
        qs = qs.filter(company_id=company_id)

    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if date_from:
        qs = qs.filter(start_date__gte=date_from)
    if date_to:
        qs = qs.filter(end_date__lte=date_to)

    page = paginate(request, qs, per_page=20)

    return render(
        request,
        "superadmin/bookings.html",
        {
            "page_obj": page,
            "bookings": page.object_list,
            "companies": Company.objects.all(),
            "statuses": Booking.Status.choices,
            "query": query,
            "status": status or "",
            "company_id": company_id or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "querystring": querystring(request, page=None),
            "active_nav": "bookings",
        },
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@superadmin_required
def users(request):
    qs = User.objects.filter(is_superuser=False).select_related("company")

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
        )

    state = request.GET.get("state")
    if state == "active":
        qs = qs.filter(is_active=True)
    elif state == "inactive":
        qs = qs.filter(is_active=False)

    page = paginate(request, qs.order_by("-date_joined"), per_page=20)

    return render(
        request,
        "superadmin/users.html",
        {
            "page_obj": page,
            "users": page.object_list,
            "query": query,
            "state": state or "",
            "querystring": querystring(request, page=None),
            "active_nav": "users",
        },
    )


@superadmin_required
@require_POST
def user_toggle(request, user_id):
    user_obj = get_object_or_404(User, pk=user_id)

    if user_obj.is_superuser:
        messages.error(request, _("Super admin accounts cannot be deactivated here."))
        return redirect("superadmin_users")

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])

    audit_service.record(
        AuditLog.Action.USER_ACTIVATED
        if user_obj.is_active
        else AuditLog.Action.USER_DEACTIVATED,
        request=request,
        entity=user_obj,
        description=f"{'Activated' if user_obj.is_active else 'Deactivated'} {user_obj.username}",
    )

    messages.success(
        request,
        _("%(user)s %(state)s.")
        % {
            "user": user_obj.username,
            "state": _("activated") if user_obj.is_active else _("deactivated"),
        },
    )
    return redirect("superadmin_users")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@superadmin_required
def contact_messages(request):
    qs = ContactMessage.objects.all()

    state = request.GET.get("state")
    if state == "unread":
        qs = qs.filter(is_read=False)
    elif state == "replied":
        qs = qs.exclude(reply="")

    page = paginate(request, qs, per_page=20)

    return render(
        request,
        "superadmin/messages.html",
        {
            "page_obj": page,
            "message_list": page.object_list,
            "unread_count": ContactMessage.objects.unread().count(),
            "state": state or "",
            "querystring": querystring(request, page=None),
            "active_nav": "messages",
        },
    )


@superadmin_required
def contact_message_detail(request, message_id):
    message_obj = get_object_or_404(ContactMessage, pk=message_id)

    if request.method == "POST":
        message_obj.reply = (request.POST.get("reply") or "").strip()
        message_obj.replied_at = timezone.now()
        message_obj.is_read = True
        message_obj.save(update_fields=["reply", "replied_at", "is_read"])
        messages.success(request, _("Reply saved."))
        return redirect("superadmin_messages")

    if not message_obj.is_read:
        message_obj.is_read = True
        message_obj.save(update_fields=["is_read"])

    return render(
        request,
        "superadmin/message_detail.html",
        {"message_obj": message_obj, "active_nav": "messages"},
    )


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------


@superadmin_required
def activity_log(request):
    qs = AuditLog.objects.with_actor()

    action = request.GET.get("action")
    if action:
        qs = qs.filter(action=action)

    company_id = request.GET.get("company")
    if company_id:
        qs = qs.filter(company_id=company_id)

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(description__icontains=query) | Q(actor_label__icontains=query)
        )

    page = paginate(request, qs, per_page=30)

    return render(
        request,
        "superadmin/activity.html",
        {
            "page_obj": page,
            "entries": page.object_list,
            "actions": AuditLog.Action.choices,
            "companies": Company.objects.all(),
            "action": action or "",
            "company_id": company_id or "",
            "query": query,
            "querystring": querystring(request, page=None),
            "active_nav": "activity",
        },
    )


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------


@superadmin_required
def global_search(request):
    """Small JSON endpoint backing the command palette."""
    from django.http import JsonResponse
    from django.urls import reverse

    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    results = []

    for company in Company.objects.filter(name__icontains=query)[:5]:
        results.append(
            {
                "type": _("Company"),
                "label": company.name,
                "meta": company.get_status_display(),
                "url": reverse("superadmin_company_edit", args=[company.pk]),
            }
        )

    for car in (
        Car.objects.select_related("company")
        .filter(Q(name__icontains=query) | Q(brand__icontains=query))[:5]
    ):
        results.append(
            {
                "type": _("Vehicle"),
                "label": car.title,
                "meta": car.company.name,
                "url": reverse("car_detail", args=[car.pk]),
            }
        )

    for booking in (
        Booking.objects.select_related("company")
        .filter(Q(reference__icontains=query) | Q(full_name__icontains=query))[:5]
    ):
        results.append(
            {
                "type": _("Booking"),
                "label": f"{booking.reference} · {booking.full_name}",
                "meta": booking.company.name,
                "url": reverse("superadmin_bookings") + f"?q={booking.reference}",
            }
        )

    for customer in Customer.objects.select_related("company").filter(
        Q(full_name__icontains=query) | Q(email__icontains=query)
    )[:5]:
        results.append(
            {
                "type": _("Customer"),
                "label": customer.full_name,
                "meta": customer.company.name,
                "url": reverse("superadmin_companies") + f"?q={customer.company.name}",
            }
        )

    return JsonResponse({"results": results[:12]})

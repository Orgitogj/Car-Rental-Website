from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ..access import (
    company_manage_required,
    company_member_required,
    enforce_manage,
    ensure_can_manage,
    get_context,
)
from ..forms import CarForm, CompanyProfileForm, ExtraForm
from ..models import Booking, Car, CarImage, Customer, Extra, MaintenanceRecord
from ..selectors import metrics
from ..services import bookings as booking_service
from ..services import fleet as fleet_service
from ..utils import paginate, querystring


@company_member_required
def dashboard(request):
    company = get_context(request).company
    period = 30

    return render(
        request,
        "company/dashboard.html",
        {
            "company": company,
            "m": metrics.company_dashboard(company, days=period),
            "revenue_series": metrics.company_revenue_series(company, days=period),
            "upcoming": metrics.company_upcoming(company),
            "attention": metrics.company_attention(company),
            "fleet_breakdown": metrics.company_fleet_breakdown(company),
            "active_nav": "dashboard",
        },
    )


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------


@company_member_required
def bookings(request):
    company = get_context(request).company

    qs = Booking.objects.for_company(company).with_display_data()

    status = request.GET.get("status")
    if status in Booking.Status.values:
        qs = qs.filter(status=status)

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(reference__icontains=query)
            | Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(car__name__icontains=query)
            | Q(car__brand__icontains=query)
        )

    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if date_from:
        qs = qs.filter(start_date__gte=date_from)
    if date_to:
        qs = qs.filter(end_date__lte=date_to)

    counts = Booking.objects.for_company(company).aggregate(
        all=Count("id"),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        confirmed=Count("id", filter=Q(status=Booking.Status.CONFIRMED)),
        cancelled=Count("id", filter=Q(status=Booking.Status.CANCELLED)),
    )

    page = paginate(request, qs, per_page=20)

    return render(
        request,
        "company/bookings.html",
        {
            "company": company,
            "page_obj": page,
            "bookings": page.object_list,
            "counts": counts,
            "status": status or "",
            "query": query,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "querystring": querystring(request, page=None),
            "statuses": Booking.Status.choices,
            "active_nav": "bookings",
        },
    )


@company_manage_required
@require_POST
def booking_confirm(request, booking_id):
    context = get_context(request)
    booking = get_object_or_404(Booking, pk=booking_id, company=context.company)
    booking_service.confirm_booking(context, booking, request=request)
    messages.success(request, _("Booking %(ref)s confirmed.") % {"ref": booking.reference})
    return redirect(request.POST.get("next") or "company_bookings")


@company_manage_required
@require_POST
def booking_cancel(request, booking_id):
    context = get_context(request)
    booking = get_object_or_404(Booking, pk=booking_id, company=context.company)
    booking_service.cancel_booking(context, booking, request=request)
    messages.success(request, _("Booking %(ref)s cancelled.") % {"ref": booking.reference})
    return redirect(request.POST.get("next") or "company_bookings")


@company_manage_required
@require_POST
def bookings_bulk(request):
    context = get_context(request)
    ids = request.POST.getlist("booking_ids")
    action = request.POST.get("action")

    if not ids:
        messages.info(request, _("Select at least one booking first."))
        return redirect("company_bookings")

    changed = booking_service.bulk_update_bookings(context, ids, action, request=request)
    if changed:
        messages.success(
            request,
            _("%(n)d booking(s) updated.") % {"n": changed},
        )
    else:
        messages.info(request, _("Nothing to update."))
    return redirect("company_bookings")


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


@company_member_required
def fleet(request):
    company = get_context(request).company

    qs = (
        Car.objects.for_company(company)
        .prefetch_related("images")
        .annotate(
            booking_count=Count("bookings", distinct=True),
            active_count=Count(
                "bookings",
                filter=Q(
                    bookings__status=Booking.Status.CONFIRMED,
                    bookings__start_date__lte=timezone.localdate(),
                    bookings__end_date__gt=timezone.localdate(),
                ),
                distinct=True,
            ),
        )
    )

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(brand__icontains=query))

    category = request.GET.get("type")
    if category in Car.Category.values:
        qs = qs.filter(car_type=category)

    availability = request.GET.get("availability")
    if availability == "listed":
        qs = qs.filter(is_active=True)
    elif availability == "unlisted":
        qs = qs.filter(is_active=False)

    page = paginate(request, qs.order_by("-is_active", "brand", "name"), per_page=12)

    return render(
        request,
        "company/fleet.html",
        {
            "company": company,
            "page_obj": page,
            "cars": page.object_list,
            "query": query,
            "category": category or "",
            "availability": availability or "",
            "categories": Car.Category.choices,
            "querystring": querystring(request, page=None),
            "active_nav": "fleet",
        },
    )


@company_manage_required
def car_create(request):
    context = get_context(request)
    form = CarForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            car = fleet_service.save_car(context, form, request=request)
            uploads = request.FILES.getlist("images")
            if uploads:
                fleet_service.add_car_images(context, car, uploads, request=request)
        except ValidationError as exc:
            form.add_error("images", exc)
        else:
            messages.success(request, _("%(car)s added to your fleet.") % {"car": car.title})
            return redirect("company_fleet")

    form.add_error_classes()
    return render(
        request,
        "company/car_form.html",
        {"form": form, "mode": "create", "active_nav": "fleet"},
    )


@company_manage_required
def car_edit(request, car_id):
    context = get_context(request)
    car = get_object_or_404(
        Car.objects.prefetch_related("images"), pk=car_id, company=context.company
    )
    form = CarForm(request.POST or None, instance=car)

    if request.method == "POST" and form.is_valid():
        try:
            fleet_service.save_car(context, form, request=request, instance=car)
            uploads = request.FILES.getlist("images")
            if uploads:
                fleet_service.add_car_images(context, car, uploads, request=request)
        except ValidationError as exc:
            form.add_error("images", exc)
        else:
            messages.success(request, _("%(car)s updated.") % {"car": car.title})
            return redirect("company_fleet")

    form.add_error_classes()
    return render(
        request,
        "company/car_form.html",
        {
            "form": form,
            "car": car,
            "images": car.images.all(),
            "mode": "edit",
            "active_nav": "fleet",
        },
    )


@company_manage_required
@require_POST
def car_delete(request, car_id):
    context = get_context(request)
    car = get_object_or_404(Car, pk=car_id, company=context.company)
    title = car.title
    fleet_service.delete_car(context, car, request=request)
    messages.success(request, _("%(car)s removed.") % {"car": title})
    return redirect("company_fleet")


@company_manage_required
@require_POST
def car_toggle(request, car_id):
    context = get_context(request)
    car = get_object_or_404(Car, pk=car_id, company=context.company)
    fleet_service.set_car_active(context, car, not car.is_active, request=request)
    messages.success(
        request,
        _("%(car)s is now %(state)s.")
        % {"car": car.title, "state": _("listed") if car.is_active else _("unlisted")},
    )
    return redirect(request.POST.get("next") or "company_fleet")


@company_manage_required
@require_POST
def car_image_delete(request, image_id):
    context = get_context(request)
    image = get_object_or_404(
        CarImage.objects.select_related("car"),
        pk=image_id,
        car__company=context.company,
    )
    car = fleet_service.delete_car_image(context, image, request=request)
    messages.success(request, _("Photo removed."))
    return redirect("company_car_edit", car_id=car.pk)


@company_manage_required
@require_POST
def car_image_main(request, image_id):
    context = get_context(request)
    image = get_object_or_404(
        CarImage.objects.select_related("car"),
        pk=image_id,
        car__company=context.company,
    )
    car = fleet_service.set_main_image(context, image, request=request)
    messages.success(request, _("Cover photo updated."))
    return redirect("company_car_edit", car_id=car.pk)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@company_member_required
def customers(request):
    company = get_context(request).company

    qs = Customer.objects.for_company(company).with_booking_stats()

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    page = paginate(request, qs.order_by("-last_booked_at", "full_name"), per_page=20)

    return render(
        request,
        "company/customers.html",
        {
            "company": company,
            "page_obj": page,
            "customers": page.object_list,
            "query": query,
            "querystring": querystring(request, page=None),
            "active_nav": "customers",
        },
    )


@company_member_required
def customer_detail(request, customer_id):
    company = get_context(request).company
    customer = get_object_or_404(Customer, pk=customer_id, company=company)

    return render(
        request,
        "company/customer_detail.html",
        {
            "company": company,
            "customer": customer,
            "bookings": customer.bookings.select_related("car").order_by("-created_at"),
            "lifetime_value": customer.lifetime_value(),
            "active_nav": "customers",
        },
    )


# ---------------------------------------------------------------------------
# Pricing / extras
# ---------------------------------------------------------------------------


@company_member_required
def pricing(request):
    context = get_context(request)
    company = context.company

    form = ExtraForm(request.POST or None)

    if request.method == "POST":
        enforce_manage(request, "change pricing", description="pricing")
        if form.is_valid():
            extra = form.save(commit=False)
            extra.company = company
            extra.save()
            messages.success(request, _("Add-on saved."))
            return redirect("company_pricing")

    form.add_error_classes()
    return render(
        request,
        "company/pricing.html",
        {
            "company": company,
            "extras": company.extras.all(),
            "cars": Car.objects.for_company(company).order_by("brand", "name"),
            "form": form,
            "active_nav": "pricing",
        },
    )


@company_manage_required
@require_POST
def extra_delete(request, extra_id):
    context = get_context(request)
    # Mutates inline rather than through a service, so it repeats the check the
    # service layer would otherwise make.
    ensure_can_manage(context, "remove add-ons")
    extra = get_object_or_404(Extra, pk=extra_id, company=context.company)
    extra.delete()
    messages.success(request, _("Add-on removed."))
    return redirect("company_pricing")


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


@company_member_required
def maintenance(request):
    company = get_context(request).company

    records = (
        MaintenanceRecord.objects.filter(company=company)
        .select_related("car")
        .order_by("-scheduled_for")
    )

    status = request.GET.get("status")
    if status in MaintenanceRecord.Status.values:
        records = records.filter(status=status)

    page = paginate(request, records, per_page=20)

    return render(
        request,
        "company/maintenance.html",
        {
            "company": company,
            "page_obj": page,
            "records": page.object_list,
            "cars": Car.objects.for_company(company).order_by("brand", "name"),
            "statuses": MaintenanceRecord.Status.choices,
            "kinds": MaintenanceRecord.Kind.choices,
            "status": status or "",
            "querystring": querystring(request, page=None),
            "active_nav": "maintenance",
        },
    )


@company_manage_required
@require_POST
def maintenance_create(request):
    context = get_context(request)
    ensure_can_manage(context, "schedule maintenance")
    car = get_object_or_404(Car, pk=request.POST.get("car"), company=context.company)

    MaintenanceRecord.objects.create(
        car=car,
        company=context.company,
        kind=request.POST.get("kind") or MaintenanceRecord.Kind.SERVICE,
        scheduled_for=request.POST.get("scheduled_for") or timezone.localdate(),
        cost=request.POST.get("cost") or 0,
        notes=(request.POST.get("notes") or "")[:2000],
    )
    messages.success(request, _("Maintenance scheduled."))
    return redirect("company_maintenance")


@company_manage_required
@require_POST
def maintenance_complete(request, record_id):
    context = get_context(request)
    ensure_can_manage(context, "complete maintenance")
    record = get_object_or_404(
        MaintenanceRecord, pk=record_id, company=context.company
    )
    record.status = MaintenanceRecord.Status.COMPLETED
    record.completed_on = timezone.localdate()
    record.save(update_fields=["status", "completed_on"])
    messages.success(request, _("Marked as completed."))
    return redirect("company_maintenance")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@company_member_required
def company_settings(request):
    context = get_context(request)
    company = context.company

    form = CompanyProfileForm(
        request.POST or None, request.FILES or None, instance=company
    )

    if request.method == "POST":
        from ..services.companies import _apply_logo

        enforce_manage(
            request, "change company settings", description="company_settings"
        )
        if form.is_valid():
            updated = form.save(commit=False)
            _apply_logo(updated, form.cleaned_data.get("logo"))
            updated.save()
            messages.success(request, _("Company profile updated."))
            return redirect("company_settings")

    form.add_error_classes()
    return render(
        request,
        "company/settings.html",
        {"company": company, "form": form, "active_nav": "settings"},
    )

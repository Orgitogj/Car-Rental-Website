from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from ..forms import BookingLookupForm, ContactForm
from ..models import Booking, Car, Company
from ..selectors import search as search_selectors
from ..services import bookings as booking_service
from ..services.bookings import BookingError
from ..utils import paginate, querystring

def home(request):
    featured = list(
        Car.objects.bookable()
        .with_display_data()
        .order_by("-popularity", "-year")[:6]
    )

    companies = (
        Company.objects.visible_to_public()
        .annotate(fleet_count=Count("cars", filter=Q(cars__is_active=True)))
        .filter(fleet_count__gt=0)
        .order_by("-fleet_count", "name")[:8]
    )

    stats = {
        "vehicles": Car.objects.bookable().count(),
        "companies": companies.count(),
        "bookings": Booking.objects.confirmed().count(),
    }

    facets = search_selectors.facet_data()

    return render(
        request,
        "public/home.html",
        {
            "featured_cars": featured,
            "companies": companies,
            "stats": stats,
            "facets": facets,
            "today": timezone.localdate().isoformat(),
        },
    )


def cars(request):
    
    filters = search_selectors.parse_filters(request.GET)
    queryset = search_selectors.search_cars(filters)
    page = paginate(request, queryset, per_page=12)
    facets = search_selectors.facet_data()

    context = {
        "page_obj": page,
        "cars": page.object_list,
        "total_count": page.paginator.count,
        "filters": filters,
        "facets": facets,
        "sort_options": search_selectors.SORT_LABELS,
        "current_sort": filters.sort,
        "querystring": querystring(request, page=None),
        "today": timezone.localdate().isoformat(),
    }

    if request.headers.get("X-Partial") == "results":
        return render(request, "public/_car_results.html", context)

    return render(request, "public/cars.html", context)


def car_detail(request, car_id):
    
    car = get_object_or_404(
        Car.objects.select_related("company").prefetch_related("images"),
        pk=car_id,
        is_active=True,
        company__status=Company.Status.ACTIVE,
    )

    extras = car.company.extras.filter(is_active=True)

    similar = (
        Car.objects.bookable()
        .with_display_data()
        .filter(car_type=car.car_type)
        .exclude(pk=car.pk)[:3]
    )

    return render(
        request,
        "public/car_detail.html",
        {
            "car": car,
            "images": list(car.images.all()),
            "extras": extras,
            "similar_cars": similar,
            "today": timezone.localdate().isoformat(),
            "min_days": settings.MIN_RENTAL_DAYS,
            "start": request.GET.get("start", ""),
            "end": request.GET.get("end", ""),
        },
    )


def checkout(request, car_id):
   
    car = get_object_or_404(
        Car.objects.select_related("company").prefetch_related("images"),
        pk=car_id,
        is_active=True,
        company__status=Company.Status.ACTIVE,
    )

    source = request.POST if request.method == "POST" else request.GET
    start_date = parse_date(source.get("start", "") or "")
    end_date = parse_date(source.get("end", "") or "")
    extra_ids = source.getlist("extras")

    if not start_date or not end_date:
        messages.info(request, _("Please choose your rental dates first."))
        return redirect("car_detail", car_id=car.pk)

    try:
        quote = booking_service.build_quote(car, start_date, end_date, extra_ids)
    except BookingError as exc:
        messages.error(request, exc.message)
        return redirect("car_detail", car_id=car.pk)

    available = booking_service.is_available(car, start_date, end_date)
    form_data = {
        "full_name": (source.get("full_name") or "").strip(),
        "email": (source.get("email") or "").strip(),
        "phone": (source.get("phone") or "").strip(),
    }
    errors = {}

    if request.method == "POST" and source.get("confirm"):
        if not available:
            errors["general"] = _("Those dates are no longer available.")
        if not form_data["full_name"] or len(form_data["full_name"]) < 3:
            errors["full_name"] = _("Please enter your full name.")
        if "@" not in form_data["email"]:
            errors["email"] = _("Please enter a valid email address.")
        if len([c for c in form_data["phone"] if c.isdigit()]) < 8:
            errors["phone"] = _("Please enter a valid phone number.")
        if not source.get("terms"):
            errors["terms"] = _("Please confirm you meet the rental requirements.")

        if not errors:
            try:
                booking = booking_service.create_booking(
                    car_id=car.pk,
                    full_name=form_data["full_name"],
                    email=form_data["email"],
                    phone=form_data["phone"],
                    start_date=start_date,
                    end_date=end_date,
                    extra_ids=extra_ids,
                    request=request,
                )
            except BookingError as exc:
                errors["general"] = exc.message
            else:
                return redirect("booking_success", reference=booking.reference)

    return render(
        request,
        "public/checkout.html",
        {
            "car": car,
            "quote": quote,
            "start_date": start_date,
            "end_date": end_date,
            "selected_extra_ids": [str(e) for e in extra_ids],
            "available": available,
            "form_data": form_data,
            "errors": errors,
        },
    )


def booking_success(request, reference):
    booking = get_object_or_404(
        Booking.objects.select_related("car", "company").prefetch_related("extras"),
        reference=reference,
    )
    return render(request, "public/booking_success.html", {"booking": booking})


def booking_lookup(request):

    booking = None
    form = BookingLookupForm(request.POST or None)
    searched = False

    if request.method == "POST":
        searched = True
        if form.is_valid():
            booking = (
                Booking.objects.select_related("car", "company")
                .prefetch_related("extras")
                .filter(
                    reference__iexact=form.cleaned_data["reference"],
                    full_name__iexact=form.cleaned_data["full_name"],
                )
                .first()
            )

    return render(
        request,
        "public/booking_lookup.html",
        {"form": form, "booking": booking, "searched": searched},
    )


def about(request):
    stats = {
        "vehicles": Car.objects.bookable().count(),
        "companies": Company.objects.visible_to_public().count(),
        "bookings": Booking.objects.confirmed().count(),
    }
    return render(request, "public/about.html", {"stats": stats})
COMPANY_ENQUIRY_SUBJECT = gettext_lazy("List my company on Vantage Rentals")


def how_it_works(request):
    hero_car = (
        Car.objects.bookable()
        .with_display_data()
        .filter(images__isnull=False)
        .distinct()
        .order_by("-popularity", "-year")
        .first()
    )
    return render(request, "public/how_it_works.html", {"hero_car": hero_car})


def functionalities(request):
    today = timezone.localdate()
    bookable = Car.objects.bookable()

    stats = {
        "vehicles": bookable.count(),
        "available": bookable.exclude(
            bookings__status__in=Booking.BLOCKING_STATUSES,
            bookings__start_date__lte=today,
            bookings__end_date__gt=today,
        ).count(),
        "bookings": Booking.objects.blocking().count(),
        "companies": Company.objects.visible_to_public().count(),
    }

    return render(
        request,
        "public/functionalities.html",
        {"stats": stats, "enquiry_subject": COMPANY_ENQUIRY_SUBJECT},
    )


def contact(request):
    initial = {}
    subject = (request.GET.get("subject") or "").strip()
    if subject:
        initial["subject"] = subject[:200]

    form = ContactForm(request.POST or None, initial=initial)
    sent = False

    if request.method == "POST" and form.is_valid():
        form.save()
        sent = True
        form = ContactForm()
        messages.success(
            request, _("Thanks for getting in touch. We'll reply within one business day.")
        )

    form.add_error_classes()
    return render(request, "public/contact.html", {"form": form, "sent": sent})

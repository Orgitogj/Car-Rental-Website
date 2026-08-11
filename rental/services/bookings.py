import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _
from ..access import ensure_can_manage, ensure_same_company
from ..models import AuditLog, Booking, BookingExtra, Car, Extra
from . import audit
from .customers import upsert_customer

logger = logging.getLogger("rental.bookings")

ZERO = Decimal("0.00")
class BookingError(Exception):

    def __init__(self, message, code="invalid", status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status

def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def overlapping_bookings(car, start_date, end_date, exclude_pk=None):
    qs = Booking.objects.filter(
        car=car,
        status__in=Booking.BLOCKING_STATUSES,
        start_date__lt=end_date,
        end_date__gt=start_date,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def is_available(car, start_date, end_date, exclude_pk=None):
    return not overlapping_bookings(car, start_date, end_date, exclude_pk).exists()

AVAILABILITY_DAYS = 365


def occupied_nights(car, since=None, until=None, exclude_pk=None):
    
    since = since or timezone.localdate()
    until = until or since + timedelta(days=AVAILABILITY_DAYS)

    qs = Booking.objects.filter(
        car=car,
        status__in=Booking.BLOCKING_STATUSES,
        start_date__lt=until,
        end_date__gt=since,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    nights = set()
    for start, end in qs.values_list("start_date", "end_date"):
        day = max(start, since)
        last = min(end, until)
        while day < last:
            nights.add(day)
            day += timedelta(days=1)

    return sorted(nights)


def availability_window(car, days=AVAILABILITY_DAYS):
    today = timezone.localdate()
    until = today + timedelta(days=days)

    return {
        "car_id": car.pk,
        "today": today.isoformat(),
        "until": until.isoformat(),
        "min_days": settings.MIN_RENTAL_DAYS,
        "price_per_day": str(money(car.price_per_day)),
        "unavailable": [d.isoformat() for d in occupied_nights(car, today, until)],
    }


def validate_dates(start_date, end_date, min_days=None):
    if not start_date or not end_date:
        raise BookingError(_("Please choose a pick-up and return date."), "missing_dates")

    if start_date < timezone.localdate():
        raise BookingError(_("The pick-up date cannot be in the past."), "past_date")

    days = (end_date - start_date).days
    if days < 1:
        raise BookingError(
            _("The return date must be after the pick-up date."), "bad_range"
        )

    minimum = settings.MIN_RENTAL_DAYS if min_days is None else min_days
    if days < minimum:
        raise BookingError(
            _("The minimum rental period is %(n)d days.") % {"n": minimum},
            "too_short",
        )

    return days


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


@dataclass
class Quote:
    days: int = 0
    price_per_day: Decimal = ZERO
    base_total: Decimal = ZERO
    extras_total: Decimal = ZERO
    total: Decimal = ZERO
    extras: list = field(default_factory=list)

    def as_dict(self):
        return {
            "days": self.days,
            "price_per_day": str(self.price_per_day),
            "base_total": str(self.base_total),
            "extras_total": str(self.extras_total),
            "total": str(self.total),
            "extras": [
                {
                    "id": e["extra"].pk,
                    "name": e["extra"].name,
                    "price_per_day": str(e["extra"].price_per_day),
                    "total": str(e["total"]),
                }
                for e in self.extras
            ],
        }


def resolve_extras(car, extra_ids):
    if not extra_ids:
        return []

    cleaned = []
    for raw in extra_ids:
        try:
            cleaned.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not cleaned:
        return []

    return list(
        Extra.objects.filter(
            pk__in=cleaned, company_id=car.company_id, is_active=True
        ).order_by("sort_order", "name")
    )


def build_quote(car, start_date, end_date, extra_ids=None, min_days=None):
    days = validate_dates(start_date, end_date, min_days=min_days)

    price_per_day = money(car.price_per_day)
    base_total = money(price_per_day * days)

    extras = []
    extras_total = ZERO
    for extra in resolve_extras(car, extra_ids or []):
        line_total = money(Decimal(extra.price_per_day) * days)
        extras_total += line_total
        extras.append({"extra": extra, "total": line_total})

    extras_total = money(extras_total)

    return Quote(
        days=days,
        price_per_day=price_per_day,
        base_total=base_total,
        extras_total=extras_total,
        total=money(base_total + extras_total),
        extras=extras,
    )


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


@transaction.atomic
def create_booking(
    *,
    car_id,
    full_name,
    email,
    phone,
    start_date,
    end_date,
    extra_ids=None,
    request=None,
):
   
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    phone = (phone or "").strip()

    if not full_name or not email or not phone:
        raise BookingError(_("Please fill in your name, email and phone number."))
    car = (
        Car.objects.select_for_update()
        .select_related("company")
        .filter(pk=car_id, is_active=True)
        .first()
    )
    if car is None:
        raise BookingError(_("This vehicle is no longer available."), "not_found", 404)

    if not car.company.is_active:
        raise BookingError(
            _("This vehicle is not currently bookable."), "company_inactive", 409
        )

    quote = build_quote(car, start_date, end_date, extra_ids)

    if not is_available(car, start_date, end_date):
        raise BookingError(
            _("Those dates were just taken. Please choose different dates."),
            "unavailable",
            409,
        )

    customer = upsert_customer(
        company=car.company, full_name=full_name, email=email, phone=phone
    )

    booking = Booking.objects.create(
        car=car,
        company=car.company,
        customer=customer,
        full_name=full_name,
        email=email,
        phone=phone,
        start_date=start_date,
        end_date=end_date,
        days=quote.days,
        price_per_day=quote.price_per_day,
        base_total=quote.base_total,
        extras_total=quote.extras_total,
        total_price=quote.total,
        status=Booking.Status.PENDING,
    )

    if quote.extras:
        BookingExtra.objects.bulk_create(
            [
                BookingExtra(
                    booking=booking,
                    extra=line["extra"],
                    name=line["extra"].name,
                    price_per_day=line["extra"].price_per_day,
                    total=line["total"],
                )
                for line in quote.extras
            ]
        )

    Car.objects.filter(pk=car.pk).update(popularity=F("popularity") + 1)

    audit.record(
        AuditLog.Action.BOOKING_CREATED,
        request=request,
        company=car.company,
        entity=booking,
        description=f"Booking {booking.reference} for {car.title}",
        metadata={"total": str(quote.total), "days": quote.days},
    )
    transaction.on_commit(lambda: _send_received_email(booking.pk))

    return booking


# ---------------------------------------------------------------------------
# State changes 
# ---------------------------------------------------------------------------


@transaction.atomic
def confirm_booking(context, booking, request=None):
    ensure_can_manage(context, "confirm bookings")
    ensure_same_company(context, booking)

    if booking.status != Booking.Status.PENDING:
        return booking

    booking.status = Booking.Status.CONFIRMED
    booking.confirmed_at = timezone.now()
    booking.save(update_fields=["status", "confirmed_at", "updated_at"])

    audit.record(
        AuditLog.Action.BOOKING_CONFIRMED,
        request=request,
        company=booking.company,
        entity=booking,
        description=f"Confirmed {booking.reference}",
    )
    return booking


@transaction.atomic
def cancel_booking(context, booking, request=None):
    ensure_can_manage(context, "cancel bookings")
    ensure_same_company(context, booking)

    if booking.status == Booking.Status.CANCELLED:
        return booking

    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at", "updated_at"])

    audit.record(
        AuditLog.Action.BOOKING_CANCELLED,
        request=request,
        company=booking.company,
        entity=booking,
        description=f"Cancelled {booking.reference}",
    )
    return booking


@transaction.atomic
def bulk_update_bookings(context, booking_ids, action, request=None):
    ensure_can_manage(context, "update bookings")

    if action not in {"confirm", "cancel"}:
        return 0

    bookings = list(
        Booking.objects.filter(
            pk__in=booking_ids,
            company=context.company,
            status=Booking.Status.PENDING,
        )
    )

    handler = confirm_booking if action == "confirm" else cancel_booking
    for booking in bookings:
        handler(context, booking, request=request)

    return len(bookings)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _send_received_email(booking_pk):
    from django.core.mail import EmailMessage

    booking = (
        Booking.objects.select_related("car", "company").filter(pk=booking_pk).first()
    )
    if booking is None:
        return

    currency = settings.DEFAULT_CURRENCY_SYMBOL
    body = _(
        "Hello %(name)s,\n\n"
        "We have received your booking request and our team is reviewing it. "
        "You will hear from us shortly.\n\n"
        "Reference: %(ref)s\n"
        "Vehicle: %(car)s\n"
        "Pick-up: %(start)s\n"
        "Return: %(end)s\n"
        "Total: %(currency)s%(total)s\n\n"
        "Thank you for choosing %(company)s."
    ) % {
        "name": booking.full_name,
        "ref": booking.reference,
        "car": booking.car.title,
        "start": booking.start_date,
        "end": booking.end_date,
        "currency": currency,
        "total": booking.total_price,
        "company": booking.company.name,
    }

    try:
        EmailMessage(
            subject=_("Booking received – %(ref)s") % {"ref": booking.reference},
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.email],
        ).send(fail_silently=True)
    except Exception:  
        logger.exception("Could not send booking email for %s", booking.reference)

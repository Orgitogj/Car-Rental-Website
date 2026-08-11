from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from ..models import Booking, Car, Company, ContactMessage, Customer

ZERO = Decimal("0.00")

_money = DecimalField(max_digits=14, decimal_places=2)


def _sum_money(field, filter=None):
    return Coalesce(Sum(field, filter=filter), Value(ZERO), output_field=_money)


def percent_change(current, previous):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)
    if previous == 0:
        return None
    return float((current - previous) / previous * 100)


class Trend:
    def __init__(self, value, previous=None, prefix="", suffix=""):
        self.value = value
        self.previous = previous
        self.prefix = prefix
        self.suffix = suffix

    @property
    def change(self):
        return percent_change(self.value, self.previous)

    @property
    def direction(self):
        change = self.change
        if change is None:
            return "flat"
        if change > 0.5:
            return "up"
        if change < -0.5:
            return "down"
        return "flat"


# ---------------------------------------------------------------------------
# Company dashboard
# ---------------------------------------------------------------------------


def company_dashboard(company, days=30):
    today = timezone.localdate()
    period_start = today - timedelta(days=days)
    previous_start = period_start - timedelta(days=days)

    bookings = Booking.objects.filter(company=company)
    confirmed = bookings.filter(status=Booking.Status.CONFIRMED)

    revenue = confirmed.aggregate(
        today=_sum_money("total_price", Q(created_at__date=today)),
        period=_sum_money("total_price", Q(created_at__date__gte=period_start)),
        previous=_sum_money(
            "total_price",
            Q(created_at__date__gte=previous_start, created_at__date__lt=period_start),
        ),
        lifetime=_sum_money("total_price"),
    )

    counts = bookings.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(created_at__date=today)),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        period=Count("id", filter=Q(created_at__date__gte=period_start)),
        previous=Count(
            "id",
            filter=Q(
                created_at__date__gte=previous_start, created_at__date__lt=period_start
            ),
        ),
        active_now=Count(
            "id",
            filter=Q(
                status=Booking.Status.CONFIRMED,
                start_date__lte=today,
                end_date__gt=today,
            ),
        ),
    )

    fleet = Car.objects.filter(company=company).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
    )

    on_road = counts["active_now"] or 0
    active_fleet = fleet["active"] or 0
    utilisation = round((on_road / active_fleet) * 100) if active_fleet else 0

    return {
        "revenue_today": Trend(revenue["today"]),
        "revenue_period": Trend(revenue["period"], revenue["previous"]),
        "revenue_lifetime": Trend(revenue["lifetime"]),
        "bookings_today": Trend(counts["today"]),
        "bookings_period": Trend(counts["period"], counts["previous"]),
        "bookings_total": Trend(counts["total"]),
        "pending_count": counts["pending"] or 0,
        "active_rentals": on_road,
        "fleet_total": fleet["total"] or 0,
        "fleet_active": active_fleet,
        "fleet_available": max(active_fleet - on_road, 0),
        "utilisation": utilisation,
        "customers_total": Customer.objects.filter(company=company).count(),
        "period_days": days,
    }


def company_revenue_series(company, days=30):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = (
        Booking.objects.filter(
            company=company,
            status=Booking.Status.CONFIRMED,
            created_at__date__gte=start,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=_sum_money("total_price"), count=Count("id"))
        .order_by("day")
    )

    by_day = {row["day"]: row for row in rows}

    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = by_day.get(day)
        series.append(
            {
                "date": day,
                "label": day.strftime("%d %b"),
                "value": float(row["total"]) if row else 0.0,
                "count": row["count"] if row else 0,
            }
        )
    return series


def company_upcoming(company, limit=5):
    today = timezone.localdate()
    horizon = today + timedelta(days=14)

    base = Booking.objects.filter(
        company=company, status=Booking.Status.CONFIRMED
    ).select_related("car")

    return {
        "pickups": list(
            base.filter(start_date__gte=today, start_date__lte=horizon).order_by(
                "start_date"
            )[:limit]
        ),
        "returns": list(
            base.filter(end_date__gte=today, end_date__lte=horizon).order_by(
                "end_date"
            )[:limit]
        ),
    }


def company_attention(company, limit=5):
    today = timezone.localdate()

    pending = (
        Booking.objects.filter(company=company, status=Booking.Status.PENDING)
        .select_related("car")
        .order_by("start_date")[:limit]
    )
    overdue = (
        Booking.objects.filter(
            company=company, status=Booking.Status.CONFIRMED, end_date__lt=today
        )
        .select_related("car")
        .order_by("end_date")[:limit]
    )
    idle = (
        Car.objects.filter(company=company, is_active=True)
        .annotate(booking_count=Count("bookings"))
        .filter(booking_count=0)[:limit]
    )

    return {"pending": list(pending), "overdue": list(overdue), "never_booked": list(idle)}


def company_fleet_breakdown(company):
    rows = (
        Car.objects.filter(company=company, is_active=True)
        .values("car_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    labels = dict(Car.Category.choices)
    return [
        {"label": str(labels.get(row["car_type"], row["car_type"])), "count": row["count"]}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Platform dashboard
# ---------------------------------------------------------------------------


def platform_dashboard(days=30):
    today = timezone.localdate()
    period_start = today - timedelta(days=days)
    previous_start = period_start - timedelta(days=days)

    companies = Company.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Company.Status.ACTIVE)),
        suspended=Count("id", filter=Q(status=Company.Status.SUSPENDED)),
        pending=Count("id", filter=Q(status=Company.Status.PENDING)),
        new_period=Count("id", filter=Q(created_at__date__gte=period_start)),
        new_previous=Count(
            "id",
            filter=Q(
                created_at__date__gte=previous_start, created_at__date__lt=period_start
            ),
        ),
    )

    bookings = Booking.objects.aggregate(
        total=Count("id"),
        period=Count("id", filter=Q(created_at__date__gte=period_start)),
        previous=Count(
            "id",
            filter=Q(
                created_at__date__gte=previous_start, created_at__date__lt=period_start
            ),
        ),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        active_now=Count(
            "id",
            filter=Q(
                status=Booking.Status.CONFIRMED,
                start_date__lte=today,
                end_date__gt=today,
            ),
        ),
    )

    revenue = Booking.objects.filter(status=Booking.Status.CONFIRMED).aggregate(
        lifetime=_sum_money("total_price"),
        period=_sum_money("total_price", Q(created_at__date__gte=period_start)),
        previous=_sum_money(
            "total_price",
            Q(created_at__date__gte=previous_start, created_at__date__lt=period_start),
        ),
    )

    fleet = Car.objects.aggregate(
        total=Count("id"), active=Count("id", filter=Q(is_active=True))
    )

    on_road = bookings["active_now"] or 0
    active_fleet = fleet["active"] or 0

    return {
        "companies_total": Trend(companies["total"]),
        "companies_active": Trend(companies["active"]),
        "companies_new": Trend(companies["new_period"], companies["new_previous"]),
        "companies_suspended": companies["suspended"] or 0,
        "companies_pending": companies["pending"] or 0,
        "fleet_total": Trend(fleet["total"]),
        "fleet_active": active_fleet,
        "bookings_total": Trend(bookings["total"]),
        "bookings_period": Trend(bookings["period"], bookings["previous"]),
        "bookings_pending": bookings["pending"] or 0,
        "active_rentals": on_road,
        "revenue_lifetime": Trend(revenue["lifetime"]),
        "revenue_period": Trend(revenue["period"], revenue["previous"]),
        "utilisation": round((on_road / active_fleet) * 100) if active_fleet else 0,
        "users_total": User.objects.filter(is_superuser=False).count(),
        "customers_total": Customer.objects.count(),
        "unread_messages": ContactMessage.objects.unread().count(),
        "period_days": days,
    }


def platform_revenue_series(days=30):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = (
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED, created_at__date__gte=start
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=_sum_money("total_price"), count=Count("id"))
        .order_by("day")
    )
    by_day = {row["day"]: row for row in rows}

    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = by_day.get(day)
        series.append(
            {
                "date": day,
                "label": day.strftime("%d %b"),
                "value": float(row["total"]) if row else 0.0,
                "count": row["count"] if row else 0,
            }
        )
    return series


def top_companies(limit=5, days=30):
    period_start = timezone.localdate() - timedelta(days=days)

    return list(
        Company.objects.annotate(
            revenue=_sum_money(
                "bookings__total_price",
                Q(
                    bookings__status=Booking.Status.CONFIRMED,
                    bookings__created_at__date__gte=period_start,
                ),
            ),
            booking_count=Count(
                "bookings",
                filter=Q(bookings__created_at__date__gte=period_start),
                distinct=True,
            ),
            fleet_count=Count("cars", filter=Q(cars__is_active=True), distinct=True),
        )
        .order_by("-revenue", "name")[:limit]
    )


def company_table_queryset():
    return (
        Company.objects.select_related("owner")
        .prefetch_related("contracts")
        .annotate(
            fleet_count=Count("cars", filter=Q(cars__is_active=True), distinct=True),
            booking_count=Count("bookings", distinct=True),
            revenue=_sum_money(
                "bookings__total_price", Q(bookings__status=Booking.Status.CONFIRMED)
            ),
            last_booking_at=Max("bookings__created_at"),
        )
    )

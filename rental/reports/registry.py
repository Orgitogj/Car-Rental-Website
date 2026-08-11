from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ..models import AuditLog, Booking, Car, Company, Customer, MaintenanceRecord
from .workbook import Column, ReportWorkbook

ZERO = Decimal("0.00")
_money = DecimalField(max_digits=14, decimal_places=2)


def _sum(field, filter=None):
    return Coalesce(Sum(field, filter=filter), Value(ZERO), output_field=_money)


@dataclass
class Filters:
    date_from: str = ""
    date_to: str = ""
    status: str = ""
    company_id: str = ""

    @classmethod
    def from_request(cls, request):
        return cls(
            date_from=(request.GET.get("from") or "").strip(),
            date_to=(request.GET.get("to") or "").strip(),
            status=(request.GET.get("status") or "").strip(),
            company_id=(request.GET.get("company") or "").strip(),
        )

    def describe(self):
        parts = []
        if self.date_from or self.date_to:
            parts.append(
                "%s → %s"
                % (self.date_from or _("start"), self.date_to or _("today"))
            )
        if self.status:
            parts.append(_("status: %(status)s") % {"status": self.status})
        return " · ".join(parts) or _("All records")

    def apply_dates(self, qs, field="created_at__date"):
        if self.date_from:
            qs = qs.filter(**{f"{field}__gte": self.date_from})
        if self.date_to:
            qs = qs.filter(**{f"{field}__lte": self.date_to})
        return qs


# ---------------------------------------------------------------------------
# Column sets
# ---------------------------------------------------------------------------

def _yes_no(flag):
    return _("Yes") if flag else _("No")


BOOKING_COLUMNS = [
    Column(_("Reference"), "reference", 16),
    Column(_("Status"), lambda b: b.get_status_display(), 13),
    Column(_("Vehicle"), lambda b: b.car.title if b.car else "", 26),
    Column(_("Category"), lambda b: b.car.get_car_type_display() if b.car else "", 14),
    Column(_("Customer"), "full_name", 24),
    Column(_("Email"), "email", 28),
    Column(_("Phone"), "phone", 16),
    Column(_("Pick-up"), "start_date", 13, "date"),
    Column(_("Return"), "end_date", 13, "date"),
    Column(_("Days"), "days", 8, "number", total=True),
    Column(_("Rate/day"), "price_per_day", 13, "money"),
    Column(_("Base"), "base_total", 13, "money", total=True),
    Column(_("Extras"), "extras_total", 13, "money", total=True),
    Column(_("Total"), "total_price", 14, "money", total=True),
    Column(_("Booked on"), "created_at", 18, "datetime"),
]

FLEET_COLUMNS = [
    Column(_("Brand"), "brand", 16),
    Column(_("Model"), "name", 22),
    Column(_("Category"), lambda c: c.get_car_type_display(), 14),
    Column(_("Year"), "year", 9, "number"),
    Column(_("Fuel"), lambda c: c.get_fuel_display(), 12),
    Column(_("Gearbox"), lambda c: c.get_gear_display(), 13),
    Column(_("Seats"), "seats", 8, "number"),
    Column(_("Doors"), "doors", 8, "number"),
    Column(_("Power (HP)"), "power", 12, "number"),
    Column(_("Rate/day"), "price_per_day", 13, "money"),
    Column(_("Listed"), lambda c: _yes_no(c.is_active), 10),
    Column(_("Bookings"), lambda c: getattr(c, "booking_count", 0), 11, "number", total=True),
    Column(
        _("Revenue"),
        lambda c: getattr(c, "revenue_total", ZERO) or ZERO,
        14,
        "money",
        total=True,
    ),
]

CUSTOMER_COLUMNS = [
    Column(_("Name"), "full_name", 26),
    Column(_("Email"), "email", 30),
    Column(_("Phone"), "phone", 18),
    Column(_("Bookings"), lambda c: getattr(c, "bookings_total", 0), 11, "number", total=True),
    Column(_("Confirmed"), lambda c: getattr(c, "confirmed_total", 0), 11, "number", total=True),
    Column(
        _("Lifetime value"),
        lambda c: getattr(c, "spend_total", ZERO) or ZERO,
        16,
        "money",
        total=True,
    ),
    Column(_("First booking"), "first_booked_at", 18, "datetime"),
    Column(_("Last booking"), "last_booked_at", 18, "datetime"),
]

COMPANY_COLUMNS = [
    Column(_("Company"), "name", 26),
    Column(_("Status"), lambda c: c.get_status_display(), 13),
    Column(_("Owner"), lambda c: c.owner.get_full_name() or c.owner.username, 26),
    Column(_("Email"), "email", 28),
    Column(_("Phone"), "phone", 16),
    Column(_("City"), "city", 16),
    Column(_("Fleet"), lambda c: getattr(c, "fleet_count", 0), 10, "number", total=True),
    Column(_("Bookings"), lambda c: getattr(c, "booking_count", 0), 11, "number", total=True),
    Column(_("Revenue"), lambda c: getattr(c, "revenue", ZERO) or ZERO, 15, "money", total=True),
    Column(_("Joined"), "created_at", 18, "datetime"),
]

MAINTENANCE_COLUMNS = [
    Column(_("Vehicle"), lambda r: r.car.title, 26),
    Column(_("Type"), lambda r: r.get_kind_display(), 16),
    Column(_("Status"), lambda r: r.get_status_display(), 14),
    Column(_("Scheduled"), "scheduled_for", 13, "date"),
    Column(_("Completed"), "completed_on", 13, "date"),
    Column(_("Cost"), "cost", 13, "money", total=True),
    Column(_("Notes"), "notes", 40),
]

AUDIT_COLUMNS = [
    Column(_("When"), "created_at", 19, "datetime"),
    Column(_("Actor"), "actor_label", 24),
    Column(_("Action"), lambda e: e.get_action_display(), 28),
    Column(_("Company"), lambda e: e.company.name if e.company else "—", 22),
    Column(_("Detail"), "description", 44),
    Column(_("IP"), "ip_address", 16),
]

USER_COLUMNS = [
    Column(_("Username"), "username", 28),
    Column(_("Name"), lambda u: u.get_full_name() or "—", 24),
    Column(_("Email"), "email", 28),
    Column(_("Company"), lambda u: getattr(getattr(u, "company", None), "name", "—"), 22),
    Column(_("Active"), lambda u: _yes_no(u.is_active), 10),
    Column(_("Joined"), "date_joined", 18, "datetime"),
    Column(_("Last login"), "last_login", 18, "datetime"),
]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _bookings_qs(filters, company=None):
    qs = Booking.objects.select_related("car", "company", "customer")
    if company is not None:
        qs = qs.filter(company=company)
    elif filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    if filters.status in Booking.Status.values:
        qs = qs.filter(status=filters.status)

    return filters.apply_dates(qs).order_by("-created_at")


def _fleet_qs(filters, company=None):
    qs = Car.objects.select_related("company")
    if company is not None:
        qs = qs.filter(company=company)
    elif filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    return qs.annotate(
        booking_count=Count("bookings", distinct=True),
        revenue_total=_sum(
            "bookings__total_price", Q(bookings__status=Booking.Status.CONFIRMED)
        ),
    ).order_by("company__name", "brand", "name")


def _customers_qs(filters, company=None):
    qs = Customer.objects.select_related("company")
    if company is not None:
        qs = qs.filter(company=company)
    elif filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    return qs.with_booking_stats().order_by("-last_booked_at")


def _revenue_summary(qs):
    return qs.aggregate(
        gross=_sum("total_price"),
        confirmed=_sum("total_price", Q(status=Booking.Status.CONFIRMED)),
        pending=_sum("total_price", Q(status=Booking.Status.PENDING)),
        cancelled=_sum("total_price", Q(status=Booking.Status.CANCELLED)),
        extras=_sum("extras_total", Q(status=Booking.Status.CONFIRMED)),
        count=Count("id"),
        confirmed_count=Count("id", filter=Q(status=Booking.Status.CONFIRMED)),
    )


def _daily_rows(qs):
    return list(
        qs.filter(status=Booking.Status.CONFIRMED)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=_sum("total_price"), count=Count("id"))
        .order_by("day")
    )


DAILY_COLUMNS = [
    Column(_("Date"), lambda r: r["day"], 14, "date"),
    Column(_("Bookings"), lambda r: r["count"], 12, "number", total=True),
    Column(_("Revenue"), lambda r: r["total"], 15, "money", total=True),
]


def _title(report_name, scope_label):
    """`Bookings – Acme Rentals`, in the reader's language."""
    return "%s – %s" % (report_name, scope_label)


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------


def build_bookings(filters, company=None, scope_label=""):
    qs = _bookings_qs(filters, company)
    wb = ReportWorkbook(_title(_("Bookings"), scope_label), filters.describe())
    wb.add_sheet(_("Bookings"), BOOKING_COLUMNS, qs, filters.describe(), "Bookings")
    return wb, "bookings"


def build_fleet(filters, company=None, scope_label=""):
    qs = _fleet_qs(filters, company)
    columns = list(FLEET_COLUMNS)
    if company is None:
        columns.insert(0, Column(_("Company"), lambda c: c.company.name, 24))

    wb = ReportWorkbook(_title(_("Fleet"), scope_label), filters.describe())
    wb.add_sheet(_("Fleet"), columns, qs, filters.describe(), "Fleet")
    return wb, "fleet"


def build_customers(filters, company=None, scope_label=""):
    qs = _customers_qs(filters, company)
    columns = list(CUSTOMER_COLUMNS)
    if company is None:
        columns.insert(0, Column(_("Company"), lambda c: c.company.name, 24))

    wb = ReportWorkbook(_title(_("Customers"), scope_label), filters.describe())
    wb.add_sheet(_("Customers"), columns, qs, filters.describe(), "Customers")
    return wb, "customers"


def build_revenue(filters, company=None, scope_label=""):
    qs = _bookings_qs(filters, company)
    summary = _revenue_summary(qs)

    wb = ReportWorkbook(_title(_("Revenue"), scope_label), filters.describe())

    wb.add_summary_sheet(
        _("Summary"),
        [
            (_("Bookings in period"), summary["count"], "number"),
            (_("Confirmed bookings"), summary["confirmed_count"], "number"),
            (_("Confirmed revenue"), summary["confirmed"], "money"),
            (_("Of which add-ons"), summary["extras"], "money"),
            (_("Pending (not yet earned)"), summary["pending"], "money"),
            (_("Cancelled value"), summary["cancelled"], "money"),
            (_("Gross booked value"), summary["gross"], "money"),
            (
                _("Average confirmed booking"),
                (
                    summary["confirmed"] / summary["confirmed_count"]
                    if summary["confirmed_count"]
                    else ZERO
                ),
                "money",
            ),
        ],
        filters.describe(),
    )

    wb.add_sheet(
        _("Daily"),
        DAILY_COLUMNS,
        _daily_rows(qs),
        _("Confirmed revenue per day"),
        "Daily",
    )

    vehicle_rows = (
        _fleet_qs(filters, company)
        .filter(bookings__isnull=False)
        .distinct()
    )
    vehicle_columns = [
        Column(_("Vehicle"), lambda c: c.title, 26),
        Column(_("Category"), lambda c: c.get_car_type_display(), 14),
        Column(_("Rate/day"), "price_per_day", 13, "money"),
        Column(_("Bookings"), lambda c: getattr(c, "booking_count", 0), 11, "number", total=True),
        Column(_("Revenue"), lambda c: getattr(c, "revenue_total", ZERO) or ZERO, 15, "money", total=True),
    ]
    if company is None:
        vehicle_columns.insert(0, Column(_("Company"), lambda c: c.company.name, 24))

    wb.add_sheet(
        _("By vehicle"),
        vehicle_columns,
        vehicle_rows,
        _("Confirmed revenue per vehicle"),
        "ByVehicle",
    )
    wb.add_sheet(_("Bookings"), BOOKING_COLUMNS, qs, filters.describe(), "RevenueBookings")

    return wb, "revenue"


def build_maintenance(filters, company=None, scope_label=""):
    qs = MaintenanceRecord.objects.select_related("car", "company")
    if company is not None:
        qs = qs.filter(company=company)
    elif filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    qs = filters.apply_dates(qs, "scheduled_for").order_by("-scheduled_for")

    columns = list(MAINTENANCE_COLUMNS)
    if company is None:
        columns.insert(0, Column(_("Company"), lambda r: r.company.name, 24))

    wb = ReportWorkbook(_title(_("Maintenance"), scope_label), filters.describe())
    wb.add_sheet(_("Maintenance"), columns, qs, filters.describe(), "Maintenance")
    return wb, "maintenance"


def build_companies(filters, company=None, scope_label="Platform"):
    qs = Company.objects.select_related("owner").annotate(
        fleet_count=Count("cars", filter=Q(cars__is_active=True), distinct=True),
        booking_count=Count("bookings", distinct=True),
        revenue=_sum("bookings__total_price", Q(bookings__status=Booking.Status.CONFIRMED)),
    )

    if filters.status in Company.Status.values:
        qs = qs.filter(status=filters.status)

    qs = filters.apply_dates(qs).order_by("name")

    wb = ReportWorkbook(_title(_("Companies"), _("Platform")), filters.describe())
    wb.add_summary_sheet(
        _("Summary"),
        [
            (_("Companies"), qs.count(), "number"),
            (_("Active"), qs.filter(status=Company.Status.ACTIVE).count(), "number"),
            (_("Pending"), qs.filter(status=Company.Status.PENDING).count(), "number"),
            (_("Suspended"), qs.filter(status=Company.Status.SUSPENDED).count(), "number"),
        ],
        filters.describe(),
    )
    wb.add_sheet(_("Companies"), COMPANY_COLUMNS, qs, filters.describe(), "Companies")
    return wb, "companies"


def build_users(filters, company=None, scope_label="Platform"):
    qs = User.objects.filter(is_superuser=False).select_related("company")
    qs = filters.apply_dates(qs, "date_joined__date").order_by("-date_joined")

    wb = ReportWorkbook(_title(_("Users"), _("Platform")), filters.describe())
    wb.add_sheet(_("Users"), USER_COLUMNS, qs, filters.describe(), "Users")
    return wb, "users"


def build_activity(filters, company=None, scope_label="Platform"):
    qs = AuditLog.objects.with_actor()
    if company is not None:
        qs = qs.filter(company=company)
    elif filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    qs = filters.apply_dates(qs).order_by("-created_at")[:10000]

    wb = ReportWorkbook(_title(_("Activity log"), scope_label), filters.describe())
    wb.add_sheet(_("Activity"), AUDIT_COLUMNS, qs, filters.describe(), "Activity")
    return wb, "activity"


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


@dataclass
class ReportDef:
    key: str
    label: str
    description: str
    builder: object
    icon: str = "sheet"


COMPANY_REPORTS = [
    ReportDef("bookings", _("Bookings"), _("Every booking with dates, pricing and customer."), build_bookings, "calendar"),
    ReportDef("revenue", _("Revenue"), _("Summary, daily trend and per-vehicle earnings."), build_revenue, "trend"),
    ReportDef("fleet", _("Fleet"), _("Vehicle specifications with booking and revenue totals."), build_fleet, "car"),
    ReportDef("customers", _("Customers"), _("Customer list with lifetime value."), build_customers, "users"),
    ReportDef("maintenance", _("Maintenance"), _("Scheduled and completed work with costs."), build_maintenance, "wrench"),
]

PLATFORM_REPORTS = [
    ReportDef("companies", _("Companies"), _("All companies with fleet, bookings and revenue."), build_companies, "building"),
    ReportDef("bookings", _("Bookings"), _("Platform-wide bookings, filterable by company."), build_bookings, "calendar"),
    ReportDef("revenue", _("Revenue"), _("Platform revenue summary and daily trend."), build_revenue, "trend"),
    ReportDef("fleet", _("Fleet"), _("Every vehicle on the platform."), build_fleet, "car"),
    ReportDef("customers", _("Customers"), _("All customers across companies."), build_customers, "users"),
    ReportDef("users", _("Users"), _("Registered accounts and their status."), build_users, "user"),
    ReportDef("activity", _("Activity log"), _("Audit trail of administrative actions."), build_activity, "shield"),
]


def find(reports, key):
    for report in reports:
        if report.key == key:
            return report
    return None

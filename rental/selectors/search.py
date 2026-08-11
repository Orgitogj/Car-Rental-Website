"""
Public vehicle search.

Turns query parameters into a filtered queryset plus a normalised description
of the active filters, so the template can render chips, keep state across
pagination, and the controller stays three lines long.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Max, Min, Q
from django.utils.dateparse import parse_date

from ..models import Car, Company

SORT_OPTIONS = {
    "recommended": ("-popularity", "name"),
    "price-asc": ("price_per_day", "name"),
    "price-desc": ("-price_per_day", "name"),
    "year-desc": ("-year", "name"),
    "year-asc": ("year", "name"),
    "seats-desc": ("-seats", "name"),
}

SORT_LABELS = {
    "recommended": "Recommended",
    "price-asc": "Price: low to high",
    "price-desc": "Price: high to low",
    "year-desc": "Newest first",
    "year-asc": "Oldest first",
    "seats-desc": "Most seats",
}


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class SearchFilters:
    start: date = None
    end: date = None
    price_min: Decimal = None
    price_max: Decimal = None
    year_min: int = None
    year_max: int = None
    seats_min: int = None
    power_min: int = None
    brands: list = field(default_factory=list)
    fuels: list = field(default_factory=list)
    gears: list = field(default_factory=list)
    types: list = field(default_factory=list)
    company_id: int = None
    query: str = ""
    sort: str = "recommended"

    @property
    def is_active(self):
        """True when the visitor has narrowed the results in any way."""
        return any(
            [
                self.start,
                self.end,
                self.price_min is not None,
                self.price_max is not None,
                self.year_min,
                self.year_max,
                self.seats_min,
                self.power_min,
                self.brands,
                self.fuels,
                self.gears,
                self.types,
                self.company_id,
                self.query,
            ]
        )

    @property
    def active_count(self):
        groups = [
            bool(self.start and self.end),
            self.price_min is not None or self.price_max is not None,
            bool(self.year_min or self.year_max),
            bool(self.seats_min),
            bool(self.power_min),
            bool(self.brands),
            bool(self.fuels),
            bool(self.gears),
            bool(self.types),
            bool(self.company_id),
            bool(self.query),
        ]
        return sum(1 for g in groups if g)


def parse_filters(params):
    """Read filters out of a QueryDict, ignoring anything malformed."""
    start = parse_date(params.get("start", "") or "")
    end = parse_date(params.get("end", "") or "")

    # An incomplete or backwards range is treated as no range at all rather
    # than silently returning nothing.
    if start and end and end <= start:
        start = end = None

    return SearchFilters(
        start=start,
        end=end,
        price_min=_decimal(params.get("price_min")),
        price_max=_decimal(params.get("price_max")),
        year_min=_int(params.get("year_min")),
        year_max=_int(params.get("year_max")),
        seats_min=_int(params.get("seats_min")),
        power_min=_int(params.get("power_min")),
        brands=[b for b in params.getlist("brand") if b],
        fuels=[f for f in params.getlist("fuel") if f in Car.Fuel.values],
        gears=[g for g in params.getlist("gear") if g in Car.Gear.values],
        types=[t for t in params.getlist("type") if t in Car.Category.values],
        company_id=_int(params.get("company")),
        query=(params.get("q") or "").strip()[:80],
        sort=params.get("sort") if params.get("sort") in SORT_OPTIONS else "recommended",
    )


def search_cars(filters):
    """Apply filters to the publicly bookable fleet."""
    qs = Car.objects.bookable().with_display_data()

    if filters.query:
        qs = qs.filter(
            Q(name__icontains=filters.query)
            | Q(brand__icontains=filters.query)
            | Q(company__name__icontains=filters.query)
        )

    if filters.start and filters.end:
        qs = qs.available_between(filters.start, filters.end)

    if filters.price_min is not None:
        qs = qs.filter(price_per_day__gte=filters.price_min)
    if filters.price_max is not None:
        qs = qs.filter(price_per_day__lte=filters.price_max)

    if filters.year_min:
        qs = qs.filter(year__gte=filters.year_min)
    if filters.year_max:
        qs = qs.filter(year__lte=filters.year_max)

    if filters.seats_min:
        qs = qs.filter(seats__gte=filters.seats_min)
    if filters.power_min:
        qs = qs.filter(power__gte=filters.power_min)

    if filters.brands:
        qs = qs.filter(brand__in=filters.brands)
    if filters.fuels:
        qs = qs.filter(fuel__in=filters.fuels)
    if filters.gears:
        qs = qs.filter(gear__in=filters.gears)
    if filters.types:
        qs = qs.filter(car_type__in=filters.types)
    if filters.company_id:
        qs = qs.filter(company_id=filters.company_id)

    return qs.order_by(*SORT_OPTIONS[filters.sort]).distinct()


def facet_data():
    """Choices for the filter sidebar, derived from the live fleet."""
    bookable = Car.objects.bookable()

    brands = sorted(
        {b for b in bookable.values_list("brand", flat=True).distinct() if b}
    )

    price_range = bookable.aggregate(
        low=Min("price_per_day"), high=Max("price_per_day")
    )

    return {
        "brands": brands,
        "fuels": Car.Fuel.choices,
        "gears": Car.Gear.choices,
        "types": Car.Category.choices,
        "companies": Company.objects.visible_to_public()
        .filter(cars__is_active=True)
        .distinct()
        .order_by("name"),
        "price_low": price_range["low"] or 0,
        "price_high": price_range["high"] or 500,
        "sort_options": SORT_LABELS,
    }


def querystring_without(params, *keys):
    """Copy of the query string with some keys removed (for filter chips)."""
    data = params.copy()
    for key in keys:
        data.pop(key, None)
    data.pop("page", None)
    return data.urlencode()

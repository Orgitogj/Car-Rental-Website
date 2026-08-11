"""
Backfill the fields added in 0006 for rows that already existed.

Runs before 0008 tightens the constraints (unique slug, non-null booking
company), so no existing row can violate them.
"""

from decimal import Decimal

from django.db import migrations
from django.utils.text import slugify

# The add-ons that used to be hard-coded in the car-details template, with the
# same prices, promoted to real per-company rows.
DEFAULT_EXTRAS = [
    ("Winter Tires", "snow", Decimal("50.00"), "Cold-weather tyres fitted before pickup."),
    ("GPS Navigation", "map", Decimal("30.00"), "Turn-by-turn navigation unit."),
    ("Baby Seat", "baby", Decimal("10.00"), "Certified child seat, fitted on request."),
    ("Additional Driver", "user-plus", Decimal("30.00"), "Add a second named driver."),
    ("Full Insurance Coverage", "shield", Decimal("50.00"), "Zero-excess damage cover."),
    ("WiFi Hotspot", "wifi", Decimal("15.00"), "Unlimited in-car 4G hotspot."),
]


def backfill(apps, schema_editor):
    Company = apps.get_model("rental", "Company")
    Booking = apps.get_model("rental", "Booking")
    Customer = apps.get_model("rental", "Customer")
    Extra = apps.get_model("rental", "Extra")

    # -- 1. Company slugs, unique ------------------------------------------
    used = set(
        Company.objects.exclude(slug="").values_list("slug", flat=True)
    )
    for company in Company.objects.filter(slug=""):
        base = slugify(company.name) or f"company-{company.pk}"
        slug = base
        counter = 2
        while slug in used:
            slug = f"{base}-{counter}"
            counter += 1
        used.add(slug)
        company.slug = slug
        company.save(update_fields=["slug"])

    # -- 2. Per-company extras ---------------------------------------------
    for company in Company.objects.all():
        for order, (name, icon, price, description) in enumerate(DEFAULT_EXTRAS):
            Extra.objects.get_or_create(
                company=company,
                name=name,
                defaults={
                    "icon": icon,
                    "price_per_day": price,
                    "description": description,
                    "sort_order": order,
                    "is_active": True,
                },
            )

    # -- 3. Bookings: tenant key, price snapshot, customer ------------------
    customer_cache = {}

    for booking in Booking.objects.select_related("car").all():
        updates = []

        if booking.company_id is None and booking.car_id:
            booking.company_id = booking.car.company_id
            updates.append("company")

        days = (booking.end_date - booking.start_date).days
        if days < 1:
            days = 1

        if not booking.days:
            booking.days = days
            updates.append("days")

        if not booking.price_per_day or booking.price_per_day == Decimal("0"):
            booking.price_per_day = booking.car.price_per_day
            updates.append("price_per_day")

        if not booking.base_total or booking.base_total == Decimal("0"):
            booking.base_total = booking.price_per_day * days
            updates.append("base_total")

        if not booking.total_price or booking.total_price == Decimal("0"):
            booking.total_price = booking.base_total + (
                booking.extras_total or Decimal("0")
            )
            updates.append("total_price")

        # Roll the inline contact details up into a customer record.
        if booking.customer_id is None and booking.company_id and booking.email:
            key = (booking.company_id, booking.email.strip().lower())
            customer = customer_cache.get(key)
            if customer is None:
                customer, _created = Customer.objects.get_or_create(
                    company_id=booking.company_id,
                    email=booking.email.strip().lower(),
                    defaults={
                        "full_name": booking.full_name,
                        "phone": booking.phone or "",
                        "last_booked_at": booking.created_at,
                    },
                )
                customer_cache[key] = customer
            booking.customer_id = customer.pk
            updates.append("customer")

        if updates:
            booking.save(update_fields=updates)


def unbackfill(apps, schema_editor):
    """Reversible enough to roll back: drop only what this migration created."""
    Extra = apps.get_model("rental", "Extra")
    Customer = apps.get_model("rental", "Customer")
    Booking = apps.get_model("rental", "Booking")

    Booking.objects.update(customer=None)
    Customer.objects.all().delete()
    Extra.objects.filter(name__in=[name for name, _i, _p, _d in DEFAULT_EXTRAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rental", "0006_expand_domain_model"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]

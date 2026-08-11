"""Booking and booking-extra models."""

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .companies import Company
from .customers import Customer
from .vehicles import Car


class BookingQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)

    def blocking(self):
        return self.filter(status__in=Booking.BLOCKING_STATUSES)

    def confirmed(self):
        return self.filter(status=Booking.Status.CONFIRMED)

    def pending(self):
        return self.filter(status=Booking.Status.PENDING)

    def overlapping(self, start_date, end_date):
        """Bookings that collide with [start_date, end_date) — half-open."""
        return self.filter(start_date__lt=end_date, end_date__gt=start_date)

    def active_on(self, day):
        """Confirmed rentals that are out on the road on `day`."""
        return self.confirmed().filter(start_date__lte=day, end_date__gt=day)

    def with_display_data(self):
        return self.select_related("car", "car__company", "company", "customer")

    def revenue(self):
        return self.confirmed().aggregate(total=models.Sum("total_price"))[
            "total"
        ] or Decimal("0")


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")

    #: Statuses that hold a vehicle and therefore block other bookings.
    BLOCKING_STATUSES = (Status.PENDING, Status.CONFIRMED)

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="bookings")

    # Denormalised tenant key: every tenant-scoped query filters on this
    # directly instead of joining through car, which keeps isolation checks
    # cheap and hard to forget.
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="bookings"
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)

    start_date = models.DateField()
    end_date = models.DateField()

    # Price snapshot taken at booking time; the vehicle's rate may change later.
    price_per_day = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    days = models.PositiveIntegerField(default=0)
    base_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    extras_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    reference = models.CharField(max_length=20, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["car", "status", "start_date", "end_date"]),
            models.Index(fields=["status", "start_date"]),
            models.Index(fields=["email"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="booking_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name="booking_total_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.reference} – {self.car.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        if self.car_id and not self.company_id:
            self.company_id = self.car.company_id
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        for _attempt in range(10):
            candidate = f"CR-{uuid.uuid4().hex[:8].upper()}"
            if not Booking.objects.filter(reference=candidate).exists():
                return candidate
        return f"CR-{uuid.uuid4().hex[:12].upper()}"

    # -- derived state ------------------------------------------------------

    @property
    def nights(self):
        return (self.end_date - self.start_date).days

    @property
    def is_cancellable(self):
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED)

    @property
    def is_out_on_road(self):
        today = timezone.localdate()
        return (
            self.status == self.Status.CONFIRMED
            and self.start_date <= today < self.end_date
        )

    @property
    def is_upcoming(self):
        return (
            self.status in self.BLOCKING_STATUSES
            and self.start_date > timezone.localdate()
        )

    @property
    def status_tone(self):
        return {
            self.Status.PENDING: "warning",
            self.Status.CONFIRMED: "success",
            self.Status.CANCELLED: "danger",
        }.get(self.status, "neutral")


class BookingExtra(models.Model):

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="extras"
    )
    extra = models.ForeignKey(
        "rental.Extra", on_delete=models.SET_NULL, null=True, blank=True
    )

    name = models.CharField(max_length=100)
    price_per_day = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    total = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["booking"])]

    def __str__(self):
        return f"{self.name} × {self.booking.reference}"

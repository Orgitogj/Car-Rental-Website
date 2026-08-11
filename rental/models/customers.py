from decimal import Decimal
from django.db import models
from .companies import Company


class CustomerQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)

    def with_booking_stats(self):
        from .bookings import Booking

        return self.annotate(
            bookings_total=models.Count("bookings", distinct=True),
            confirmed_total=models.Count(
                "bookings",
                filter=models.Q(bookings__status=Booking.Status.CONFIRMED),
                distinct=True,
            ),
            spend_total=models.Sum(
                "bookings__total_price",
                filter=models.Q(bookings__status=Booking.Status.CONFIRMED),
            ),
        )


class Customer(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="customers"
    )

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)

    notes = models.TextField(blank=True)

    first_booked_at = models.DateTimeField(auto_now_add=True)
    last_booked_at = models.DateTimeField(null=True, blank=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["company", "email"]),
            models.Index(fields=["company", "-last_booked_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"], name="customer_unique_email_per_company"
            )
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    @property
    def initials(self):
        parts = [p for p in self.full_name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def lifetime_value(self):
        from .bookings import Booking

        return self.bookings.filter(status=Booking.Status.CONFIRMED).aggregate(
            total=models.Sum("total_price")
        )["total"] or Decimal("0")

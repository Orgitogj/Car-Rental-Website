from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .companies import Company
class CarQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def bookable(self):
    
        return self.filter(is_active=True, company__status=Company.Status.ACTIVE)

    def for_company(self, company):
        return self.filter(company=company)

    def with_display_data(self):
        
        return self.select_related("company").prefetch_related("images")

    def available_between(self, start_date, end_date):
        from .bookings import Booking

        return self.exclude(
            bookings__status__in=Booking.BLOCKING_STATUSES,
            bookings__start_date__lt=end_date,
            bookings__end_date__gt=start_date,
        )


class Car(models.Model):
    class Fuel(models.TextChoices):
        PETROL = "petrol", _("Petrol")
        DIESEL = "diesel", _("Diesel")
        HYBRID = "hybrid", _("Hybrid")
        ELECTRIC = "electric", _("Electric")

    class Gear(models.TextChoices):
        MANUAL = "manual", _("Manual")
        AUTOMATIC = "automatic", _("Automatic")

    class Category(models.TextChoices):
        ECONOMY = "economy", _("Economy")
        FAMILY = "family", _("Family")
        SUV = "suv", _("SUV")
        LUXURY = "luxury", _("Luxury")
        SPORTS = "sports", _("Sports")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="cars"
    )

    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=50)
    car_type = models.CharField(max_length=50, choices=Category.choices)
    description = models.TextField(blank=True)

    price_per_day = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    year = models.IntegerField()
    seats = models.IntegerField()
    doors = models.IntegerField(default=4)
    bags = models.IntegerField(default=2)
    power = models.IntegerField(help_text=_("Horsepower"))
    fuel = models.CharField(max_length=20, choices=Fuel.choices)
    gear = models.CharField(max_length=20, choices=Gear.choices)
    engine_size = models.CharField(max_length=10, null=True, blank=True)

    popularity = models.IntegerField(default=0)
    is_active = models.BooleanField(
        default=True, help_text=_("Inactive vehicles are hidden from customers.")
    )

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    objects = CarQuerySet.as_manager()

    class Meta:
        ordering = ["-popularity", "name"]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["car_type"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["price_per_day"]),
            models.Index(fields=["-popularity"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_per_day__gte=0),
                name="car_price_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(seats__gt=0), name="car_seats_positive"
            ),
        ]

    def __str__(self):
        return f"{self.brand} {self.name}"

    def get_absolute_url(self):
        return reverse("car_detail", args=[self.pk])

    @property
    def title(self):
        return f"{self.brand} {self.name}"

    @property
    def main_image(self):
       
        images = list(self.images.all())
        if not images:
            return None
        for image in images:
            if image.is_main:
                return image
        return images[0]

    @property
    def image_count(self):
        return len(list(self.images.all()))


class CarImage(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="images")

    image = models.BinaryField()
    image_content_type = models.CharField(max_length=100, default="image/jpeg")
    image_name = models.CharField(max_length=255, blank=True, null=True)

    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_main", "created_at"]
        indexes = [models.Index(fields=["car", "-is_main"])]

    def __str__(self):
        return f"Image for {self.car.name}"

    @property
    def url(self):
        return reverse("car_image", args=[self.pk])


class Extra(models.Model):

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="extras"
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    icon = models.CharField(
        max_length=40, blank=True, help_text=_("Icon id from the sprite sheet.")
    )
    price_per_day = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["company", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="extra_unique_name_per_company"
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_day__gte=0),
                name="extra_price_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class MaintenanceRecord(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")

    class Kind(models.TextChoices):
        SERVICE = "service", _("Routine service")
        REPAIR = "repair", _("Repair")
        INSPECTION = "inspection", _("Inspection")
        CLEANING = "cleaning", _("Cleaning")
        TYRES = "tyres", _("Tyres")

    car = models.ForeignKey(
        Car, on_delete=models.CASCADE, related_name="maintenance_records"
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="maintenance_records"
    )

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SERVICE)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    scheduled_for = models.DateField()
    completed_on = models.DateField(null=True, blank=True)
    cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_for"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["car", "-scheduled_for"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.car.title}"

    def save(self, *args, **kwargs):
        if self.car_id and not self.company_id:
            self.company_id = self.car.company_id
        super().save(*args, **kwargs)

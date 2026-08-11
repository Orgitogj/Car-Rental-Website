from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class CompanyQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Company.Status.ACTIVE)

    def visible_to_public(self):
        return self.filter(status=Company.Status.ACTIVE)

    def with_fleet(self):
        return self.filter(cars__is_active=True).distinct()

    def with_counts(self):
        from .bookings import Booking

        return self.annotate(
            fleet_count=models.Count(
                "cars", filter=models.Q(cars__is_active=True), distinct=True
            ),
            bookings_count=models.Count("bookings", distinct=True),
            revenue_total=models.Sum(
                "bookings__total_price",
                filter=models.Q(bookings__status=Booking.Status.CONFIRMED),
            ),
        )


class Company(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        PENDING = "pending", _("Pending approval")
        SUSPENDED = "suspended", _("Suspended")

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    logo_data = models.BinaryField(blank=True, null=True, editable=True)
    logo_content_type = models.CharField(max_length=100, blank=True, null=True)
    logo_name = models.CharField(max_length=255, blank=True, null=True)

    description = models.TextField(blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)

    city = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=200, blank=True)
    website = models.URLField(blank=True)

    legal_name = models.CharField(
        max_length=150, blank=True, verbose_name=_("Legal business name")
    )
    state = models.CharField(max_length=80, blank=True, verbose_name=_("State"))
    tin = models.CharField(max_length=40, blank=True, verbose_name=_("TIN"))
    tax_number = models.CharField(
        max_length=40, blank=True, verbose_name=_("Tax number")
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"
        indexes = [
            models.Index(fields=["status", "name"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def _build_unique_slug(self):
        base = slugify(self.name) or "company"
        slug = base
        counter = 2
        while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def has_logo(self):
        return bool(self.logo_data)

    @property
    def logo_url(self):
        if not self.logo_data:
            return None
        return reverse("company_logo", args=[self.pk])

    @property
    def initials(self):
        parts = [p for p in self.name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    @property
    def current_contract(self):
        contracts = list(self.contracts.all())
        return contracts[0] if contracts else None

    @property
    def registered_name(self):
        return self.legal_name or self.name


class CompanyDocument(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="documents"
    )
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    data = models.BinaryField(editable=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["company", "-uploaded_at"])]

    def __str__(self):
        return f"{self.company.name} · {self.name}"

    @property
    def url(self):
        return reverse("company_document", args=[self.pk])

    @property
    def size_kb(self):
        return round((self.size or 0) / 1024)

"""Audit trail.

Records who did what, to which record, in which tenant. Written by the service
layer so that any code path performing a sensitive action is logged once, in one
place, rather than relying on each controller to remember.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLogQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)

    def with_actor(self):
        return self.select_related("actor", "company")


class AuditLog(models.Model):
    class Action(models.TextChoices):
        COMPANY_CREATED = "company.created", _("Company created")
        COMPANY_UPDATED = "company.updated", _("Company updated")
        COMPANY_DELETED = "company.deleted", _("Company deleted")
        COMPANY_STATUS_CHANGED = "company.status_changed", _("Company status changed")
        COMPANY_VIEWED = "company.viewed", _("Company dashboard opened (read-only)")

        VEHICLE_CREATED = "vehicle.created", _("Vehicle added")
        VEHICLE_UPDATED = "vehicle.updated", _("Vehicle updated")
        VEHICLE_DELETED = "vehicle.deleted", _("Vehicle removed")

        BOOKING_CREATED = "booking.created", _("Booking created")
        BOOKING_CONFIRMED = "booking.confirmed", _("Booking confirmed")
        BOOKING_CANCELLED = "booking.cancelled", _("Booking cancelled")

        CONTRACT_CREATED = "contract.created", _("Contract issued")
        CONTRACT_VIEWED = "contract.viewed", _("Contract opened")
        CONTRACT_SIGNED = "contract.signed", _("Contract signed")
        CONTRACT_REJECTED = "contract.rejected", _("Contract declined")
        CONTRACT_VERSION_CREATED = "contract.version_created", _("Contract version published")
        CONTRACT_RENEWAL_REQUIRED = "contract.renewal_required", _("Contract renewal required")

        USER_ACTIVATED = "user.activated", _("User activated")
        USER_DEACTIVATED = "user.deactivated", _("User deactivated")

        REPORT_EXPORTED = "report.exported", _("Report exported")

        ACCESS_DENIED = "access.denied", _("Unauthorised action blocked")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor_label = models.CharField(
        max_length=150,
        blank=True,
        help_text=_("Actor name captured at write time, survives user deletion."),
    )

    action = models.CharField(max_length=50, choices=Action.choices)
    description = models.CharField(max_length=255, blank=True)

    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.CharField(max_length=50, blank=True)

    company = models.ForeignKey(
        "rental.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.actor_label or 'system'} · {self.action}"

    @property
    def tone(self):
        if self.action == self.Action.ACCESS_DENIED:
            return "danger"
        if self.action in (
            self.Action.COMPANY_DELETED,
            self.Action.VEHICLE_DELETED,
            self.Action.BOOKING_CANCELLED,
            self.Action.USER_DEACTIVATED,
            self.Action.CONTRACT_REJECTED,
        ):
            return "warning"
        if self.action in (
            self.Action.COMPANY_VIEWED,
            self.Action.CONTRACT_VIEWED,
        ):
            return "info"
        if self.action == self.Action.CONTRACT_SIGNED:
            return "success"
        return "neutral"

import hashlib
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def content_fingerprint(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ContractImmutable(ValidationError):
    """Raised when something tries to rewrite a signed contract."""

# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

class ContractTemplateQuerySet(models.QuerySet):
    def published(self):
        return self.filter(published_at__isnull=False)

    def active(self):
        return self.filter(is_active=True)


class ContractTemplate(models.Model):
   
    version = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=150)
    summary = models.CharField(max_length=255, blank=True)
    body = models.TextField(
        help_text=_(
            "Plain text. A line starting with ## becomes a section heading; "
            "a blank line starts a new paragraph."
        )
    )

    is_active = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_templates",
    )

    objects = ContractTemplateQuerySet.as_manager()
    LOCKED_FIELDS = ("version", "title", "body")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.title} v{self.version}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded = dict(zip(field_names, values))
        return instance

    @property
    def is_locked(self):
        if not self.pk:
            return False
        return self.contracts.filter(status=CompanyContract.Status.SIGNED).exists()

    def save(self, *args, **kwargs):
        loaded = getattr(self, "_loaded", None)
        if loaded and self.is_locked:
            changed = [
                name
                for name in self.LOCKED_FIELDS
                if name in loaded and loaded[name] != getattr(self, name)
            ]
            if changed:
                raise ContractImmutable(
                    _(
                        "Contract v%(version)s has already been signed and cannot "
                        "be edited. Publish a new version instead."
                    )
                    % {"version": loaded.get("version", self.version)}
                )
        super().save(*args, **kwargs)

    @property
    def signed_count(self):
        return self.contracts.filter(status=CompanyContract.Status.SIGNED).count()

    @property
    def pending_count(self):
        return self.contracts.filter(
            status=CompanyContract.Status.PENDING_SIGNATURE
        ).count()


# ---------------------------------------------------------------------------
# Per-company contract
# ---------------------------------------------------------------------------


class CompanyContractQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=CompanyContract.Status.PENDING_SIGNATURE)

    def signed(self):
        return self.filter(status=CompanyContract.Status.SIGNED)

    def for_company(self, company):
        return self.filter(company=company)

    def with_display_data(self):
        return self.select_related("company", "template", "signed_by")


class CompanyContract(models.Model):
    class Status(models.TextChoices):
        PENDING_SIGNATURE = "pending_signature", _("Pending signature")
        SIGNED = "signed", _("Signed")
        REJECTED = "rejected", _("Rejected")
        EXPIRED = "expired", _("Expired")

    company = models.ForeignKey(
        "rental.Company", on_delete=models.CASCADE, related_name="contracts"
    )
    template = models.ForeignKey(
        ContractTemplate, on_delete=models.PROTECT, related_name="contracts"
    )

    reference = models.CharField(max_length=32, unique=True, editable=False)
    version = models.CharField(max_length=20)
    title = models.CharField(max_length=150)
    content = models.TextField()
    content_hash = models.CharField(max_length=64, editable=False)

    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_SIGNATURE,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    first_viewed_at = models.DateTimeField(null=True, blank=True)

    # -- signature ----------------------------------------------------------
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_contracts",
    )
    signer_name = models.CharField(max_length=150, blank=True)
    signer_email = models.EmailField(blank=True)
    signature_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_("What the signer typed as their signature."),
    )
    signature_hash = models.CharField(max_length=64, blank=True, editable=False)
    signature_ip = models.GenericIPAddressField(null=True, blank=True)
    signature_user_agent = models.CharField(max_length=400, blank=True)

    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    objects = CompanyContractQuerySet.as_manager()

    LOCKED_FIELDS = (
        "company_id",
        "template_id",
        "reference",
        "version",
        "title",
        "content",
        "content_hash",
        "status",
        "signed_at",
        "signed_by_id",
        "signer_name",
        "signer_email",
        "signature_name",
        "signature_hash",
        "signature_ip",
        "signature_user_agent",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "template"], name="one_contract_per_company_version"
            )
        ]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.reference} · {self.company_id} · v{self.version}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded = dict(zip(field_names, values))
        return instance

    # -- writes -------------------------------------------------------------

    def save(self, *args, **kwargs):
        loaded = getattr(self, "_loaded", None)
        if loaded and loaded.get("status") == self.Status.SIGNED:
            changed = [
                name
                for name in self.LOCKED_FIELDS
                if name in loaded and loaded[name] != getattr(self, name)
            ]
            if changed:
                raise ContractImmutable(
                    _("Contract %(reference)s is signed and can no longer be changed.")
                    % {"reference": loaded.get("reference", self.reference)}
                )

        if not self.reference:
            self.reference = self._generate_reference()
        if not self.content_hash:
            self.content_hash = content_fingerprint(self.content)

        super().save(*args, **kwargs)
        self._loaded = {
            name: getattr(self, name) for name in self.LOCKED_FIELDS if hasattr(self, name)
        }

    def delete(self, *args, **kwargs):
        if self.status == self.Status.SIGNED:
            raise ContractImmutable(
                _("Signed contracts are part of the audit trail and cannot be deleted.")
            )
        return super().delete(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        year = timezone.now().year
        for _attempt in range(10):
            candidate = f"CTR-{year}-{uuid.uuid4().hex[:8].upper()}"
            if not CompanyContract.objects.filter(reference=candidate).exists():
                return candidate
        return f"CTR-{year}-{uuid.uuid4().hex[:12].upper()}"

    # -- derived state ------------------------------------------------------

    @property
    def is_signed(self):
        return self.status == self.Status.SIGNED

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING_SIGNATURE

    @property
    def blocks_access(self):
        """Anything other than a signature keeps the panel locked."""
        return self.status != self.Status.SIGNED

    @property
    def tone(self):
        return {
            self.Status.SIGNED: "success",
            self.Status.PENDING_SIGNATURE: "warning",
            self.Status.REJECTED: "danger",
            self.Status.EXPIRED: "neutral",
        }.get(self.status, "neutral")

    @property
    def content_matches_hash(self):
        return content_fingerprint(self.content) == self.content_hash

    def build_signature_hash(self, signed_at):
        payload = "|".join(
            [
                self.reference,
                self.content_hash,
                self.signature_name.strip().lower(),
                (self.signer_email or "").strip().lower(),
                signed_at.isoformat(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

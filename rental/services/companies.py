from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from ..access import SESSION_KEY
from ..models import AuditLog, Company, CompanyDocument
from . import audit
from . import contracts as contract_service
from .fleet import validate_image

DEFAULT_EXTRAS = [
    ("Winter Tires", "snow", "50.00", "Cold-weather tyres fitted before pickup."),
    ("GPS Navigation", "map", "30.00", "Turn-by-turn navigation unit."),
    ("Baby Seat", "baby", "10.00", "Certified child seat, fitted on request."),
    ("Additional Driver", "user-plus", "30.00", "Add a second named driver."),
    ("Full Insurance Coverage", "shield", "50.00", "Zero-excess damage cover."),
    ("WiFi Hotspot", "wifi", "15.00", "Unlimited in-car 4G hotspot."),
]


def _apply_logo(company, logo_file):
    if not logo_file:
        return False
    validate_image(logo_file)
    company.logo_data = logo_file.read()
    company.logo_content_type = (logo_file.content_type or "image/jpeg").lower()
    company.logo_name = logo_file.name[:255]
    return True


def seed_default_extras(company):
    from decimal import Decimal

    from ..models import Extra

    for order, (name, icon, price, description) in enumerate(DEFAULT_EXTRAS):
        Extra.objects.get_or_create(
            company=company,
            name=name,
            defaults={
                "icon": icon,
                "price_per_day": Decimal(price),
                "description": description,
                "sort_order": order,
            },
        )


@transaction.atomic
def create_company(form, request=None):
    data = form.cleaned_data

    owner = User.objects.create_user(
        username=data["owner_email"],
        email=data["owner_email"],
        password=data["owner_password"],
    )
    owner.first_name = data["owner_full_name"][:150]
    owner.save(update_fields=["first_name"])

    company = form.save(commit=False)
    company.owner = owner
    _apply_logo(company, data.get("logo"))
    company.save()

    seed_default_extras(company)

    audit.record(
        AuditLog.Action.COMPANY_CREATED,
        request=request,
        company=company,
        entity=company,
        description=f"Created company {company.name}",
        metadata={"owner": owner.username},
    )
    return company


def attach_documents(company, uploads, uploaded_by=None):
    saved = []
    for upload in uploads or []:
        upload.seek(0)
        saved.append(
            CompanyDocument.objects.create(
                company=company,
                name=upload.name[:255],
                content_type=(upload.content_type or "application/octet-stream").lower(),
                size=upload.size or 0,
                data=upload.read(),
                uploaded_by=uploaded_by,
            )
        )
    return saved


@transaction.atomic
def register_company(form, request=None):
    data = form.cleaned_data

    owner = User.objects.create_user(
        username=data["email"],
        email=data["email"],
        password=data["password1"],
        first_name=data["first_name"][:150],
        last_name=data["last_name"][:150],
    )

    from ..accounts.models import Profile

    Profile.objects.update_or_create(
        user=owner, defaults={"phone": data.get("phone", "")}
    )

    company = Company.objects.create(
        name=data["business_name"],
        email=data["business_email"],
        phone=data.get("phone", ""),
        legal_name=data.get("legal_name", ""),
        city=data.get("city", ""),
        address=data.get("address", ""),
        state=data.get("state", ""),
        tin=data.get("tin", ""),
        tax_number=data.get("tax_number", ""),
        status=Company.Status.PENDING,
        owner=owner,
    )

    attach_documents(company, data.get("documents"), uploaded_by=owner)
    seed_default_extras(company)

    audit.record(
        AuditLog.Action.COMPANY_CREATED,
        request=request,
        actor=owner,
        company=company,
        entity=company,
        description=f"{company.name} registered through the public sign-up",
        metadata={"owner": owner.username, "self_registered": True},
    )

    contract = contract_service.issue_contract(company, request=request, actor=owner)
    return company, contract


@transaction.atomic
def update_company(form, request=None):
    company = form.save(commit=False)
    _apply_logo(company, form.cleaned_data.get("logo"))
    company.save()

    audit.record(
        AuditLog.Action.COMPANY_UPDATED,
        request=request,
        company=company,
        entity=company,
        description=f"Updated company {company.name}",
    )
    return company


@transaction.atomic
def set_company_status(company, status, request=None):
    if status not in Company.Status.values:
        raise ValidationError(_("Unknown status."))

    previous = company.status
    company.status = status
    company.save(update_fields=["status", "updated_at"])

    audit.record(
        AuditLog.Action.COMPANY_STATUS_CHANGED,
        request=request,
        company=company,
        entity=company,
        description=f"{company.name}: {previous} → {status}",
        metadata={"from": previous, "to": status},
    )
    return company


@transaction.atomic
def delete_company(company, request=None):
    name = company.name
    company_id = company.pk
    owner = company.owner

    company.delete()
    if owner and not owner.is_superuser:
        owner.delete()

    audit.record(
        AuditLog.Action.COMPANY_DELETED,
        request=request,
        entity_type="Company",
        entity_id=company_id,
        description=f"Deleted company {name}",
    )


# ---------------------------------------------------------------------------
# Read-only drill-in
# ---------------------------------------------------------------------------


def enter_company_view(request, company):
    request.session[SESSION_KEY] = company.pk

    audit.record(
        AuditLog.Action.COMPANY_VIEWED,
        request=request,
        company=company,
        entity=company,
        description=f"Opened {company.name} in read-only mode",
    )


def exit_company_view(request):
    request.session.pop(SESSION_KEY, None)

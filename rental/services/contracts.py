from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from ..contract_text import (
    DEFAULT_CONTRACT_BODY,
    DEFAULT_CONTRACT_SUMMARY,
    DEFAULT_CONTRACT_TITLE,
    DEFAULT_CONTRACT_VERSION,
)
from ..models import AuditLog, CompanyContract, ContractTemplate
from . import audit
USER_AGENT_LIMIT = 400


class ContractError(ValidationError):
    """A signing attempt that the rules refuse."""


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def active_template():

    template = ContractTemplate.objects.active().order_by("-created_at").first()
    if template is not None:
        return template

    template = ContractTemplate.objects.filter(
        version=DEFAULT_CONTRACT_VERSION
    ).first()
    if template is not None:
        return template

    return ContractTemplate.objects.create(
        version=DEFAULT_CONTRACT_VERSION,
        title=DEFAULT_CONTRACT_TITLE,
        summary=DEFAULT_CONTRACT_SUMMARY,
        body=DEFAULT_CONTRACT_BODY,
        is_active=True,
        published_at=timezone.now(),
    )


@transaction.atomic
def publish_template(
    *, version, title, body, summary="", request=None, actor=None, activate=True
):
    
    version = (version or "").strip()
    if not version:
        raise ContractError(_("A contract version is required."))
    if ContractTemplate.objects.filter(version__iexact=version).exists():
        raise ContractError(
            _("Version %(version)s already exists. Choose a new version number.")
            % {"version": version}
        )
    if not (body or "").strip():
        raise ContractError(_("The contract text cannot be empty."))

    template = ContractTemplate.objects.create(
        version=version,
        title=(title or DEFAULT_CONTRACT_TITLE).strip(),
        summary=(summary or "").strip(),
        body=body,
        is_active=activate,
        published_at=timezone.now() if activate else None,
        created_by=actor or (getattr(request, "user", None) if request else None),
    )

    if activate:
        from ..models import Company

        ContractTemplate.objects.exclude(pk=template.pk).update(is_active=False)

        # Anything still waiting on an older version is moot now; the company
        # is asked for the new one instead. Signed rows are left alone.
        expired = CompanyContract.objects.pending().exclude(template=template)
        expired.update(status=CompanyContract.Status.EXPIRED)

        # Issue the new version straight away rather than waiting for each
        # company to log in, so the console shows who still owes a signature.
        issued = 0
        for company in Company.objects.all():
            issue_contract(company, template, request=request, actor=actor)
            issued += 1

        audit.record(
            AuditLog.Action.CONTRACT_RENEWAL_REQUIRED,
            request=request,
            actor=actor,
            description=f"v{template.version} requires every company to re-sign",
            metadata={"version": template.version, "companies": issued},
        )

    audit.record(
        AuditLog.Action.CONTRACT_VERSION_CREATED,
        request=request,
        actor=actor,
        entity=template,
        description=f"Published contract v{template.version}",
        metadata={"version": template.version, "active": activate},
    )
    return template


# ---------------------------------------------------------------------------
# Issuing
# ---------------------------------------------------------------------------


@transaction.atomic
def issue_contract(company, template=None, *, request=None, actor=None):
    template = template or active_template()

    existing = CompanyContract.objects.filter(
        company=company, template=template
    ).first()
    if existing is not None:
        return existing

    contract = CompanyContract.objects.create(
        company=company,
        template=template,
        version=template.version,
        title=template.title,
        content=template.body,
    )

    audit.record(
        AuditLog.Action.CONTRACT_CREATED,
        request=request,
        actor=actor,
        company=company,
        entity=contract,
        description=f"Issued contract {contract.reference} (v{contract.version})",
        metadata={"reference": contract.reference, "version": contract.version},
    )
    return contract


def current_contract(company, *, create=True, request=None):
    if company is None:
        return None

    template = active_template()
    contract = CompanyContract.objects.filter(
        company=company, template=template
    ).first()
    if contract is not None:
        return contract

    if create:
        return issue_contract(company, template, request=request)

    return CompanyContract.objects.filter(company=company).first()


def signed_contracts(company):
    return CompanyContract.objects.for_company(company).signed().with_display_data()


def contract_history(company):
    return CompanyContract.objects.for_company(company).with_display_data()


def requires_signature(company, *, create=True):
    """True when the panel must stay locked for this company."""
    if company is None:
        return False
    contract = current_contract(company, create=create)
    return contract is None or contract.blocks_access


# ---------------------------------------------------------------------------
# Reading and signing
# ---------------------------------------------------------------------------


def mark_viewed(contract, *, request=None, actor=None):
    if contract is None or contract.first_viewed_at is not None:
        return contract

    contract.first_viewed_at = timezone.now()
    CompanyContract.objects.filter(pk=contract.pk).update(
        first_viewed_at=contract.first_viewed_at
    )

    audit.record(
        AuditLog.Action.CONTRACT_VIEWED,
        request=request,
        actor=actor,
        company=contract.company,
        entity=contract,
        description=f"{contract.company.name} opened contract {contract.reference}",
        metadata={"reference": contract.reference, "version": contract.version},
    )
    return contract


@transaction.atomic
def sign_contract(contract, *, user, signature_name, request=None):
  
    contract = (
        CompanyContract.objects.select_for_update()
        .select_related("company")
        .get(pk=contract.pk)
    )

    if contract.status == CompanyContract.Status.SIGNED:
        raise ContractError(_("This contract has already been signed."))
    if contract.status == CompanyContract.Status.EXPIRED:
        raise ContractError(
            _("This version has been superseded. Please sign the current version.")
        )
    if contract.status == CompanyContract.Status.REJECTED:
        raise ContractError(_("This contract was rejected and can no longer be signed."))

    signature_name = (signature_name or "").strip()
    if len(signature_name) < 3:
        raise ContractError(_("Please type your full name as your signature."))

    if not contract.content_matches_hash:
        raise ContractError(
            _("The contract text does not match its signature fingerprint.")
        )

    signed_at = timezone.now()
    full_name = (user.get_full_name() or "").strip() or user.username

    contract.status = CompanyContract.Status.SIGNED
    contract.signed_at = signed_at
    contract.signed_by = user
    contract.signer_name = full_name[:150]
    contract.signer_email = (user.email or "")[:254]
    contract.signature_name = signature_name[:150]
    contract.signature_ip = audit.client_ip(request)
    contract.signature_user_agent = (
        request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_LIMIT] if request else ""
    )
    contract.signature_hash = contract.build_signature_hash(signed_at)
    contract.save()

    audit.record(
        AuditLog.Action.CONTRACT_SIGNED,
        request=request,
        actor=user,
        company=contract.company,
        entity=contract,
        description=(
            f"{contract.company.name} signed contract {contract.reference} "
            f"(v{contract.version})"
        ),
        metadata={
            "reference": contract.reference,
            "version": contract.version,
            "signer": contract.signer_name,
            "signer_email": contract.signer_email,
            "signature_hash": contract.signature_hash,
            "content_hash": contract.content_hash,
        },
    )
    return contract


@transaction.atomic
def reject_contract(contract, *, user, reason="", request=None):
    if contract.status == CompanyContract.Status.SIGNED:
        raise ContractError(_("A signed contract cannot be rejected."))

    contract.status = CompanyContract.Status.REJECTED
    contract.rejected_at = timezone.now()
    contract.rejection_reason = (reason or "")[:255]
    contract.save()

    audit.record(
        AuditLog.Action.CONTRACT_REJECTED,
        request=request,
        actor=user,
        company=contract.company,
        entity=contract,
        description=f"{contract.company.name} declined contract {contract.reference}",
        metadata={"reference": contract.reference, "reason": contract.rejection_reason},
    )
    return contract


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


def contract_sections(contract_or_text):
    text = getattr(contract_or_text, "content", contract_or_text) or ""

    sections = []
    current = {"heading": None, "paragraphs": []}
    buffer = []

    def flush():
        if buffer:
            current["paragraphs"].append(" ".join(buffer).strip())
            buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            flush()
            if current["heading"] or current["paragraphs"]:
                sections.append(current)
            current = {"heading": stripped.lstrip("#").strip(), "paragraphs": []}
        elif not stripped:
            flush()
        else:
            buffer.append(stripped)

    flush()
    if current["heading"] or current["paragraphs"]:
        sections.append(current)
    return sections

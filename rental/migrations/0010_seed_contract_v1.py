import hashlib
import uuid
from django.db import migrations
from django.utils import timezone

from rental.contract_text import (
    DEFAULT_CONTRACT_BODY,
    DEFAULT_CONTRACT_SUMMARY,
    DEFAULT_CONTRACT_TITLE,
    DEFAULT_CONTRACT_VERSION,
)


def issue_v1(apps, schema_editor):
    ContractTemplate = apps.get_model("rental", "ContractTemplate")
    CompanyContract = apps.get_model("rental", "CompanyContract")
    Company = apps.get_model("rental", "Company")

    if ContractTemplate.objects.filter(version=DEFAULT_CONTRACT_VERSION).exists():
        return

    now = timezone.now()
    template = ContractTemplate.objects.create(
        version=DEFAULT_CONTRACT_VERSION,
        title=DEFAULT_CONTRACT_TITLE,
        summary=DEFAULT_CONTRACT_SUMMARY,
        body=DEFAULT_CONTRACT_BODY,
        is_active=True,
        published_at=now,
    )

    fingerprint = hashlib.sha256(template.body.encode("utf-8")).hexdigest()
    year = now.year

    CompanyContract.objects.bulk_create(
        [
            CompanyContract(
                company=company,
                template=template,
                reference=f"CTR-{year}-{uuid.uuid4().hex[:8].upper()}",
                version=template.version,
                title=template.title,
                content=template.body,
                content_hash=fingerprint,
                status="pending_signature",
            )
            for company in Company.objects.all()
        ]
    )


def withdraw_v1(apps, schema_editor):
    ContractTemplate = apps.get_model("rental", "ContractTemplate")
    CompanyContract = apps.get_model("rental", "CompanyContract")

    CompanyContract.objects.filter(version=DEFAULT_CONTRACT_VERSION).delete()
    ContractTemplate.objects.filter(version=DEFAULT_CONTRACT_VERSION).delete()


class Migration(migrations.Migration):
    dependencies = [("rental", "0009_contracts_and_business_details")]

    operations = [migrations.RunPython(issue_v1, withdraw_v1)]

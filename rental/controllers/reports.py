from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _
from ..access import company_member_required, get_context, superadmin_required
from ..models import AuditLog, Company
from ..reports import registry
from ..services import audit as audit_service

@company_member_required
def company_reports(request):
    company = get_context(request).company
    return render(
        request,
        "company/reports.html",
        {
            "company": company,
            "reports": registry.COMPANY_REPORTS,
            "active_nav": "reports",
        },
    )


@company_member_required
def company_report_export(request, key):
    context = get_context(request)
    company = context.company

    report = registry.find(registry.COMPANY_REPORTS, key)
    if report is None:
        raise Http404("Unknown report")

    filters = registry.Filters.from_request(request)
    # A company admin may never widen their own scope.
    filters.company_id = ""

    workbook, slug = report.builder(filters, company=company, scope_label=company.name)

    audit_service.record(
        AuditLog.Action.REPORT_EXPORTED,
        request=request,
        company=company,
        # Audit descriptions are stored records, so they stay in one language:
        # the report key, not the exporter's translated label.
        description=f"Exported {report.key} report",
        metadata={
            "report": key,
            "read_only": context.is_read_only,
            "filters": {
                "from": filters.date_from,
                "to": filters.date_to,
                "status": filters.status,
            },
        },
    )

    return workbook.response(f"{company.slug}-{slug}")


@superadmin_required
def platform_reports(request):
    return render(
        request,
        "superadmin/reports.html",
        {
            "reports": registry.PLATFORM_REPORTS,
            "companies": Company.objects.all(),
            "active_nav": "reports",
        },
    )


@superadmin_required
def platform_report_export(request, key):
    report = registry.find(registry.PLATFORM_REPORTS, key)
    if report is None:
        raise Http404("Unknown report")

    filters = registry.Filters.from_request(request)

    scope_company = None
    scope_label = _("Platform")
    if filters.company_id:
        scope_company = Company.objects.filter(pk=filters.company_id).first()
        if scope_company:
            scope_label = scope_company.name

    # Company-specific reports get the object; platform-wide builders read the
    # company id off the filters themselves.
    if report.key in {"companies", "users"}:
        workbook, slug = report.builder(filters, scope_label=scope_label)
    else:
        workbook, slug = report.builder(
            filters, company=scope_company, scope_label=scope_label
        )

    audit_service.record(
        AuditLog.Action.REPORT_EXPORTED,
        request=request,
        company=scope_company,
        description=f"Exported platform {report.key} report",
        metadata={"report": key, "company_filter": filters.company_id},
    )

    prefix = scope_company.slug if scope_company else "platform"
    return workbook.response(f"{prefix}-{slug}")

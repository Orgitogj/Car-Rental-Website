import json
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from ..access import get_context, superadmin_required
from ..models import Company, CompanyContract, ContractTemplate
from ..services import contracts as contract_service
from ..utils import paginate

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _company_of(request):
    if not request.user.is_authenticated:
        return None
    context = get_context(request)
    if not context.company:
        raise PermissionDenied("You are not associated with a company.")
    return context.company


def _own_contract(company, contract_id):
    return get_object_or_404(
        CompanyContract.objects.with_display_data(),
        pk=contract_id,
        company=company,
    )


def _serialise(contract, *, include_content=False):
    payload = {
        "id": contract.pk,
        "reference": contract.reference,
        "company_id": contract.company_id,
        "company": contract.company.name,
        "version": contract.version,
        "title": contract.title,
        "status": contract.status,
        "status_label": contract.get_status_display(),
        "created_at": contract.created_at.isoformat() if contract.created_at else None,
        "first_viewed_at": (
            contract.first_viewed_at.isoformat() if contract.first_viewed_at else None
        ),
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "signer": {
            "user_id": contract.signed_by_id,
            "name": contract.signer_name,
            "email": contract.signer_email,
            "signature_name": contract.signature_name,
            "signature_hash": contract.signature_hash,
            "ip_address": contract.signature_ip,
            "user_agent": contract.signature_user_agent,
        }
        if contract.is_signed
        else None,
        "content_hash": contract.content_hash,
        "requires_signature": contract.blocks_access,
    }
    if include_content:
        payload["content"] = contract.content
    return payload


def _payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or "{}")
        except (ValueError, UnicodeDecodeError):
            return None
    return request.POST.dict()


# ---------------------------------------------------------------------------
# Company — pages
# ---------------------------------------------------------------------------


def company_contract(request):
    """The contract page. Reachable whether or not the gate is closed."""
    company = _company_of(request)
    if company is None:
        return redirect("portal_login")

    context = get_context(request)
    contract = contract_service.current_contract(company, request=request)

    if contract is not None and not context.is_read_only:
        contract_service.mark_viewed(contract, request=request, actor=request.user)

    return render(
        request,
        "company/contract.html",
        {
            "company": company,
            "contract": contract,
            "sections": contract_service.contract_sections(contract),
            "history": contract_service.contract_history(company).exclude(
                pk=contract.pk if contract else None
            ),
            "signer_default": (request.user.get_full_name() or "").strip(),
            "active_nav": "contract",
        },
    )


@require_POST
def company_contract_sign(request):
    company = _company_of(request)
    if company is None:
        return redirect("portal_login")

    context = get_context(request)
    if context.is_read_only:
        raise PermissionDenied("A contract can only be signed by the company itself.")

    contract = contract_service.current_contract(company, request=request)
    if contract is None:
        messages.error(request, _("There is no contract to sign right now."))
        return redirect("company_contract")

    if request.POST.get("accept_terms") not in ("on", "true", "1", "yes"):
        messages.error(
            request, _("Please confirm that you have read and accept the contract.")
        )
        return redirect("company_contract")

    try:
        contract = contract_service.sign_contract(
            contract,
            user=request.user,
            signature_name=request.POST.get("signature_name", ""),
            request=request,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("company_contract")

    messages.success(
        request,
        _("Contract signed successfully. Your company dashboard is now open."),
    )
    return redirect("company_dashboard")


def company_contract_detail(request, contract_id):
    company = _company_of(request)
    if company is None:
        return redirect("portal_login")

    contract = _own_contract(company, contract_id)

    return render(
        request,
        "company/contract.html",
        {
            "company": company,
            "contract": contract,
            "sections": contract_service.contract_sections(contract),
            "history": contract_service.contract_history(company).exclude(
                pk=contract.pk
            ),
            "is_archive_view": True,
            "active_nav": "contract",
        },
    )


# ---------------------------------------------------------------------------
# Company — JSON API
# ---------------------------------------------------------------------------


def _api_company(request):
    if not request.user.is_authenticated:
        return None, JsonResponse({"error": _("Authentication required.")}, status=401)

    context = get_context(request)
    if not context.company:
        return None, JsonResponse(
            {"error": _("You are not associated with a company.")}, status=403
        )
    return context.company, None


@require_GET
def api_company_contract(request):
    company, refusal = _api_company(request)
    if refusal is not None:
        return refusal

    contract = contract_service.current_contract(company, request=request)
    if contract is None:
        return JsonResponse({"error": _("No contract on file.")}, status=404)

    return JsonResponse(_serialise(contract, include_content=True))


@require_GET
def api_company_contract_detail(request, contract_id):
    company, refusal = _api_company(request)
    if refusal is not None:
        return refusal

    contract = _own_contract(company, contract_id)
    return JsonResponse(_serialise(contract, include_content=True))


@require_POST
def api_company_contract_sign(request):
    company, refusal = _api_company(request)
    if refusal is not None:
        return refusal

    context = get_context(request)
    if context.is_read_only:
        return JsonResponse(
            {"error": _("A contract can only be signed by the company itself.")},
            status=403,
        )

    data = _payload(request)
    if data is None:
        return JsonResponse({"error": _("Malformed request.")}, status=400)

    if str(data.get("accept_terms")).lower() not in ("on", "true", "1", "yes"):
        return JsonResponse(
            {"error": _("Please confirm that you have read and accept the contract.")},
            status=400,
        )

    contract = contract_service.current_contract(company, request=request)
    if contract is None:
        return JsonResponse({"error": _("No contract on file.")}, status=404)

    try:
        contract = contract_service.sign_contract(
            contract,
            user=request.user,
            signature_name=data.get("signature_name", ""),
            request=request,
        )
    except ValidationError as error:
        return JsonResponse({"error": error.messages[0]}, status=400)

    return JsonResponse(
        {
            "contract": _serialise(contract),
            "redirect_url": reverse("company_dashboard"),
        }
    )
# ---------------------------------------------------------------------------
# Platform administrator
# ---------------------------------------------------------------------------
@superadmin_required
def console_contracts(request):
    qs = CompanyContract.objects.with_display_data()

    status = request.GET.get("status")
    if status in CompanyContract.Status.values:
        qs = qs.filter(status=status)

    version = request.GET.get("version")
    if version:
        qs = qs.filter(version=version)

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(company__name__icontains=query)

    page = paginate(request, qs, per_page=20)
    counts = {
        "all": CompanyContract.objects.count(),
        "signed": CompanyContract.objects.signed().count(),
        "pending": CompanyContract.objects.pending().count(),
    }

    return render(
        request,
        "superadmin/contracts.html",
        {
            "page_obj": page,
            "contracts": page.object_list,
            "counts": counts,
            "status": status or "",
            "query": query,
            "statuses": CompanyContract.Status.choices,
            "templates": ContractTemplate.objects.all(),
            "active_template": contract_service.active_template(),
            "active_nav": "contracts",
        },
    )


@superadmin_required
def console_company_contract(request, company_id):
    company = get_object_or_404(Company.objects.select_related("owner"), pk=company_id)
    contract = contract_service.current_contract(company, create=False)

    requested = request.GET.get("contract")
    if requested:
        contract = get_object_or_404(
            CompanyContract.objects.with_display_data(),
            pk=requested,
            company=company,
        )

    return render(
        request,
        "superadmin/company_contract.html",
        {
            "company": company,
            "contract": contract,
            "sections": contract_service.contract_sections(contract),
            "history": contract_service.contract_history(company),
            "documents": company.documents.all(),
            "active_nav": "companies",
        },
    )


@superadmin_required
def console_contract_template_create(request):
    current = contract_service.active_template()

    initial = {
        "version": "",
        "title": current.title if current else "",
        "summary": current.summary if current else "",
        "body": current.body if current else "",
    }
    values = dict(initial)
    error = None

    if request.method == "POST":
        values = {
            "version": request.POST.get("version", "").strip(),
            "title": request.POST.get("title", "").strip(),
            "summary": request.POST.get("summary", "").strip(),
            "body": request.POST.get("body", ""),
        }
        try:
            template = contract_service.publish_template(
                version=values["version"],
                title=values["title"],
                summary=values["summary"],
                body=values["body"],
                request=request,
                actor=request.user,
                activate=request.POST.get("activate") in ("on", "true", "1"),
            )
        except ValidationError as exc:
            error = exc.messages[0]
        else:
            messages.success(
                request,
                _("Contract v%(version)s published.") % {"version": template.version},
            )
            return redirect("superadmin_contracts")

    return render(
        request,
        "superadmin/contract_template_form.html",
        {
            "values": values,
            "error": error,
            "current": current,
            "active_nav": "contracts",
        },
    )


@superadmin_required
@require_GET
def api_console_company_contracts(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    history = contract_service.contract_history(company)
    return JsonResponse(
        {
            "company": {"id": company.pk, "name": company.name},
            "contracts": [_serialise(contract) for contract in history],
        }
    )


@superadmin_required
@require_GET
def api_console_contract_detail(request, contract_id):
    contract = get_object_or_404(
        CompanyContract.objects.with_display_data(), pk=contract_id
    )
    return JsonResponse(_serialise(contract, include_content=True))

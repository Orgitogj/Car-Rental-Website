from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

SESSION_KEY = "impersonated_company_id"
CONTRACT_SIGNATURE_REQUIRED = "CONTRACT_SIGNATURE_REQUIRED"
CONTRACT_EXEMPT_URL_NAMES = frozenset(
    {
        "company_contract",
        "company_contract_sign",
        "company_contract_detail",
        "api_company_contract",
        "api_company_contract_detail",
        "api_company_contract_sign",
        "company_logo",
        "company_document",
    }
)

CONTRACT_GUARDED_PREFIXES = ("company_", "api_company_")


class Mode:
    MANAGE = "manage"
    READ_ONLY = "read_only"


class CompanyContext:

    __slots__ = ("company", "mode", "is_impersonated")

    def __init__(self, company=None, mode=None, is_impersonated=False):
        self.company = company
        self.mode = mode
        self.is_impersonated = is_impersonated

    def __bool__(self):
        return self.company is not None

    @property
    def can_manage(self):
        return self.company is not None and self.mode == Mode.MANAGE

    @property
    def is_read_only(self):
        return self.company is not None and self.mode == Mode.READ_ONLY

    @property
    def company_id(self):
        return self.company.pk if self.company else None

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<CompanyContext {self.company} mode={self.mode}>"


EMPTY_CONTEXT = CompanyContext()


def own_company(user):
    if not user or not user.is_authenticated:
        return None
    try:
        return user.company
    except Exception:
        return None


def resolve_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return EMPTY_CONTEXT

    if user.is_superuser:
        company_id = request.session.get(SESSION_KEY)
        if not company_id:
            return EMPTY_CONTEXT

        from .models import Company

        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            # Company was deleted while being viewed — drop the stale pointer.
            request.session.pop(SESSION_KEY, None)
            return EMPTY_CONTEXT

        return CompanyContext(company, Mode.READ_ONLY, is_impersonated=True)

    company = own_company(user)
    if company is None:
        return EMPTY_CONTEXT

    return CompanyContext(company, Mode.MANAGE)


def get_context(request):
    return getattr(request, "company_context", None) or EMPTY_CONTEXT


# ---------------------------------------------------------------------------
# Service-layer guards
# ---------------------------------------------------------------------------


def ensure_can_manage(context, action="perform this action"):
    if context is None or not context.company:
        raise PermissionDenied("No company selected.")
    if not context.can_manage:
        raise PermissionDenied(
            f"This is a read-only view of {context.company.name}; "
            f"you cannot {action}."
        )


def enforce_manage(request, action="perform this action", description="", message=None):

    context = get_context(request)

    if not context.company:
        raise PermissionDenied("You are not associated with a company.")

    if context.can_manage:
        return context

    from .services.audit import record_denied_action

    record_denied_action(request, description=description or action)

    raise PermissionDenied(
        message
        or f"This is a read-only view of {context.company.name}; "
        f"you cannot {action}."
    )


def ensure_same_company(context, obj, field="company_id"):
    if context is None or not context.company:
        raise PermissionDenied("No company selected.")

    owner_id = getattr(obj, field, None)
    if owner_id is None and hasattr(obj, "company"):
        owner_id = obj.company_id

    if owner_id != context.company_id:
        raise PermissionDenied("This record belongs to a different company.")


# ---------------------------------------------------------------------------
# Onboarding gate — the contract must be signed before the panel opens
# ---------------------------------------------------------------------------


def contract_pending_for(request):
    
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.is_superuser:
        return None

    company = own_company(user)
    if company is None:
        return None

    from .services import contracts as contract_service

    contract = contract_service.current_contract(company, request=request)
    if contract is not None and contract.blocks_access:
        return contract
    return None


def wants_json(request):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if "application/json" in (request.content_type or ""):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def contract_required_response(request, contract=None):
    """The refusal an unsigned company gets: 403 for API, redirect for pages."""
    target = reverse("company_contract")

    if wants_json(request):
        return JsonResponse(
            {
                "error": _(
                    "Your company must sign the platform contract before using "
                    "this feature."
                ),
                "code": CONTRACT_SIGNATURE_REQUIRED,
                "contract_url": target,
                "contract_status": contract.status if contract else None,
            },
            status=403,
        )

    return redirect(target)


def enforce_contract(request):
    """Guard used by the panel decorators. Returns a response, or None."""
    contract = contract_pending_for(request)
    if contract is None:
        return None
    return contract_required_response(request, contract)


# ---------------------------------------------------------------------------
# Controller decorators
# ---------------------------------------------------------------------------


def _login_redirect(request):
    return redirect(f"{reverse('portal_login')}?next={request.path}")


def company_member_required(controller):
    @wraps(controller)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)

        context = get_context(request)
        if not context.company:
            raise PermissionDenied("You are not associated with a company.")

        blocked = enforce_contract(request)
        if blocked is not None:
            return blocked

        return controller(request, *args, **kwargs)

    return wrapper


def company_manage_required(controller):
    @wraps(controller)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)

        context = get_context(request)
        if not context.company:
            raise PermissionDenied("You are not associated with a company.")

        blocked = enforce_contract(request)
        if blocked is not None:
            return blocked

        enforce_manage(
            request,
            description=controller.__name__,
            message=(
                f"You are viewing {context.company.name} in read-only mode. "
                "Changes are not permitted."
            ),
        )

        return controller(request, *args, **kwargs)

    return wrapper


def superadmin_required(controller):

    @wraps(controller)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)

        if not request.user.is_superuser:
            raise PermissionDenied("Platform administrator access required.")

        return controller(request, *args, **kwargs)

    return wrapper

from django.conf import settings
from .access import get_context


def navigation(request):

    context = get_context(request)

    return {
        "company_ctx": context,
        "viewing_company": context.company,
        "is_read_only_view": context.is_read_only,
        "can_manage_company": context.can_manage,
        "CURRENCY": settings.DEFAULT_CURRENCY_SYMBOL,
        "MIN_RENTAL_DAYS": settings.MIN_RENTAL_DAYS,
    }


def contract_state(request):
    # Mirrors what the gate enforces server-side, so the panel chrome can lock
    # itself. A platform administrator drilling into a company is never locked
    # out by it — they are inspecting, and writes are refused elsewhere.
    context = get_context(request)
    company = context.company

    if company is None:
        return {"company_contract": None, "contract_locked": False}

    from .services import contracts as contract_service

    contract = contract_service.current_contract(
        company, create=not context.is_read_only, request=request
    )

    return {
        "company_contract": contract,
        "contract_locked": (
            contract is not None
            and contract.blocks_access
            and not context.is_read_only
        ),
    }

from django.utils.functional import SimpleLazyObject

from .access import (
    CONTRACT_EXEMPT_URL_NAMES,
    CONTRACT_GUARDED_PREFIXES,
    contract_pending_for,
    contract_required_response,
    resolve_context,
)


class CompanyContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company_context = SimpleLazyObject(lambda: resolve_context(request))
        return self.get_response(request)


class ContractGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        url_name = getattr(match, "url_name", None)
        if not url_name or not self._is_guarded(url_name):
            return None

        contract = contract_pending_for(request)
        if contract is None:
            return None

        return contract_required_response(request, contract)

    @staticmethod
    def _is_guarded(url_name):
        if url_name in CONTRACT_EXEMPT_URL_NAMES:
            return False
        return url_name.startswith(CONTRACT_GUARDED_PREFIXES)

from django.urls import path
from .controllers import (
    booking_api,
    company,
    contracts,
    media,
    public,
    reports,
    superadmin,
)

# ---------------------------------------------------------------------------
# Public site
# ---------------------------------------------------------------------------
public_patterns = [
    path("", public.home, name="home"),
    path("cars/", public.cars, name="cars"),
    path("cars/<int:car_id>/", public.car_detail, name="car_detail"),
    path("book/<int:car_id>/", public.checkout, name="checkout"),
    path(
        "booking/success/<str:reference>/",
        public.booking_success,
        name="booking_success",
    ),
    path("booking/lookup/", public.booking_lookup, name="booking_lookup"),
    path("about/", public.about, name="about"),
    path("how-it-works/", public.how_it_works, name="how_it_works"),
    path("functionalities/", public.functionalities, name="functionalities"),
    path("contact/", public.contact, name="contact"),
    path("media/car-image/<int:image_id>/", media.car_image, name="car_image"),
    path(
        "media/company-logo/<int:company_id>/",
        media.company_logo,
        name="company_logo",
    ),
    path(
        "media/company-document/<int:document_id>/",
        media.company_document,
        name="company_document",
    ),
]

# ---------------------------------------------------------------------------
# Company 
# ---------------------------------------------------------------------------
company_patterns = [
    path("portal/", company.dashboard, name="company_dashboard"),
    # Reachable while the contract gate is closed — see access.CONTRACT_EXEMPT_URL_NAMES.
    path("portal/contract/", contracts.company_contract, name="company_contract"),
    path(
        "portal/contract/sign/",
        contracts.company_contract_sign,
        name="company_contract_sign",
    ),
    path(
        "portal/contract/<int:contract_id>/",
        contracts.company_contract_detail,
        name="company_contract_detail",
    ),
    path("portal/bookings/", company.bookings, name="company_bookings"),
    path(
        "portal/bookings/<int:booking_id>/confirm/",
        company.booking_confirm,
        name="company_booking_confirm",
    ),
    path(
        "portal/bookings/<int:booking_id>/cancel/",
        company.booking_cancel,
        name="company_booking_cancel",
    ),
    path("portal/bookings/bulk/", company.bookings_bulk, name="company_bookings_bulk"),
    path("portal/fleet/", company.fleet, name="company_fleet"),
    path("portal/fleet/add/", company.car_create, name="company_car_create"),
    path("portal/fleet/<int:car_id>/edit/", company.car_edit, name="company_car_edit"),
    path(
        "portal/fleet/<int:car_id>/delete/",
        company.car_delete,
        name="company_car_delete",
    ),
    path(
        "portal/fleet/<int:car_id>/toggle/",
        company.car_toggle,
        name="company_car_toggle",
    ),
    path(
        "portal/fleet/image/<int:image_id>/delete/",
        company.car_image_delete,
        name="company_car_image_delete",
    ),
    path(
        "portal/fleet/image/<int:image_id>/main/",
        company.car_image_main,
        name="company_car_image_main",
    ),
    path("portal/customers/", company.customers, name="company_customers"),
    path(
        "portal/customers/<int:customer_id>/",
        company.customer_detail,
        name="company_customer_detail",
    ),
    path("portal/pricing/", company.pricing, name="company_pricing"),
    path(
        "portal/pricing/<int:extra_id>/delete/",
        company.extra_delete,
        name="company_extra_delete",
    ),
    path("portal/maintenance/", company.maintenance, name="company_maintenance"),
    path(
        "portal/maintenance/add/",
        company.maintenance_create,
        name="company_maintenance_create",
    ),
    path(
        "portal/maintenance/<int:record_id>/complete/",
        company.maintenance_complete,
        name="company_maintenance_complete",
    ),
    path("portal/reports/", reports.company_reports, name="company_reports"),
    path(
        "portal/reports/<str:key>.xlsx",
        reports.company_report_export,
        name="company_report_export",
    ),
    path("portal/settings/", company.company_settings, name="company_settings"),
]

# ---------------------------------------------------------------------------
# Platform 
# ---------------------------------------------------------------------------
console_patterns = [
    path("console/", superadmin.dashboard, name="superadmin_dashboard"),
    path("console/companies/", superadmin.companies, name="superadmin_companies"),
    path(
        "console/companies/add/",
        superadmin.company_create,
        name="superadmin_company_create",
    ),
    path(
        "console/companies/<int:company_id>/edit/",
        superadmin.company_edit,
        name="superadmin_company_edit",
    ),
    path(
        "console/companies/<int:company_id>/delete/",
        superadmin.company_delete,
        name="superadmin_company_delete",
    ),
    path(
        "console/companies/<int:company_id>/status/",
        superadmin.company_status,
        name="superadmin_company_status",
    ),
    path(
        "console/companies/<int:company_id>/view/",
        superadmin.company_enter,
        name="superadmin_company_enter",
    ),
    path("console/exit-company/", superadmin.company_exit, name="superadmin_company_exit"),
    path("console/fleet/", superadmin.fleet_overview, name="superadmin_fleet"),
    path("console/bookings/", superadmin.bookings_overview, name="superadmin_bookings"),
    path("console/users/", superadmin.users, name="superadmin_users"),
    path(
        "console/users/<int:user_id>/toggle/",
        superadmin.user_toggle,
        name="superadmin_user_toggle",
    ),
    path("console/messages/", superadmin.contact_messages, name="superadmin_messages"),
    path(
        "console/messages/<int:message_id>/",
        superadmin.contact_message_detail,
        name="superadmin_message_detail",
    ),
    path("console/contracts/", contracts.console_contracts, name="superadmin_contracts"),
    path(
        "console/contracts/new-version/",
        contracts.console_contract_template_create,
        name="superadmin_contract_template_create",
    ),
    path(
        "console/companies/<int:company_id>/contract/",
        contracts.console_company_contract,
        name="superadmin_company_contract",
    ),
    path("console/activity/", superadmin.activity_log, name="superadmin_activity"),
    path("console/reports/", reports.platform_reports, name="superadmin_reports"),
    path(
        "console/reports/<str:key>.xlsx",
        reports.platform_report_export,
        name="superadmin_report_export",
    ),
    path("console/search/", superadmin.global_search, name="superadmin_search"),
]

# ---------------------------------------------------------------------------
# JSON endpoints for the booking UI
# ---------------------------------------------------------------------------
api_patterns = [
    path(
        "api/cars/<int:car_id>/availability/",
        booking_api.availability,
        name="api_availability",
    ),
    path("api/quote/", booking_api.quote, name="api_quote"),
    path("api/bookings/create/", booking_api.create_booking, name="api_create_booking"),
    path(
        "api/company/contract/",
        contracts.api_company_contract,
        name="api_company_contract",
    ),
    path(
        "api/company/contract/sign/",
        contracts.api_company_contract_sign,
        name="api_company_contract_sign",
    ),
    path(
        "api/company/contract/<int:contract_id>/",
        contracts.api_company_contract_detail,
        name="api_company_contract_detail",
    ),
    path(
        "api/console/companies/<int:company_id>/contracts/",
        contracts.api_console_company_contracts,
        name="api_console_company_contracts",
    ),
    path(
        "api/console/contracts/<int:contract_id>/",
        contracts.api_console_contract_detail,
        name="api_console_contract_detail",
    ),
]

urlpatterns = public_patterns + company_patterns + console_patterns + api_patterns

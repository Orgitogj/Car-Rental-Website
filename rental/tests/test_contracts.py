"""The onboarding gate: registration, signing, and everything it locks.

The contract requirement is an authorisation rule, not a screen, so most of
these tests go at it the way an attacker would — straight at the URL, straight
at the API, straight at the model — rather than through the page that is meant
to be used.
"""

import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from rental.models import (
    AuditLog,
    CompanyContract,
    ContractImmutable,
    ContractTemplate,
    Company,
)
from rental.services import contracts as contract_service
from rental.tests.factories import (
    current_contract,
    make_car,
    make_company,
    make_superuser,
    sign_contract,
)

PASSWORD = "test-pass-1234"

REGISTRATION = {
    "first_name": "Arben",
    "last_name": "Hoxha",
    "email": "arben@newfleet.com",
    "phone": "+355 69 123 4567",
    "password1": "Sh0rtcut-Rentals!",
    "password2": "Sh0rtcut-Rentals!",
    "business_name": "New Fleet Rentals",
    "business_email": "contact@newfleet.com",
    "legal_name": "New Fleet Rentals sh.p.k.",
    "city": "Tirana",
    "address": "Rruga e Durrësit 12",
    "state": "Tirana",
    "tin": "K12345678L",
    "tax_number": "AL12345678",
    "accept_terms": "on",
}

#: Panel routes an unsigned company must not reach.
GUARDED_ROUTES = [
    "company_dashboard",
    "company_bookings",
    "company_fleet",
    "company_customers",
    "company_pricing",
    "company_maintenance",
    "company_reports",
    "company_settings",
]


class RegistrationTests(TestCase):
    """Test 1 — a new company lands at the contract, not the dashboard."""

    def test_registration_creates_the_company_its_owner_and_a_contract(self):
        response = self.client.post(reverse("portal_register"), REGISTRATION)

        company = Company.objects.get(name="New Fleet Rentals")
        owner = company.owner

        self.assertRedirects(response, reverse("company_contract"))
        self.assertEqual(company.status, Company.Status.PENDING)
        self.assertEqual(owner.email, "arben@newfleet.com")
        self.assertEqual(owner.get_full_name(), "Arben Hoxha")
        self.assertEqual(owner.profile.phone, "+355 69 123 4567")

        # The business details from step two are stored, not dropped.
        self.assertEqual(company.legal_name, "New Fleet Rentals sh.p.k.")
        self.assertEqual(company.state, "Tirana")
        self.assertEqual(company.tin, "K12345678L")
        self.assertEqual(company.tax_number, "AL12345678")

        contract = current_contract(company)
        self.assertEqual(contract.status, CompanyContract.Status.PENDING_SIGNATURE)
        self.assertEqual(contract.version, contract_service.active_template().version)
        self.assertTrue(contract.reference.startswith("CTR-"))

    def test_the_new_owner_is_signed_in_and_the_dashboard_is_shut(self):
        self.client.post(reverse("portal_register"), REGISTRATION)

        self.assertIn("_auth_user_id", self.client.session)

        response = self.client.get(reverse("company_dashboard"))
        self.assertRedirects(response, reverse("company_contract"))

    def test_the_contract_page_is_reachable_while_the_gate_is_closed(self):
        self.client.post(reverse("portal_register"), REGISTRATION)

        response = self.client.get(reverse("company_contract"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contract Signature Required")

    def test_a_duplicate_email_is_refused_and_nothing_is_created(self):
        User.objects.create_user(username=REGISTRATION["email"], password=PASSWORD)

        response = self.client.post(reverse("portal_register"), REGISTRATION)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Company.objects.filter(name="New Fleet Rentals").exists())

    def test_the_terms_checkbox_is_mandatory(self):
        payload = {**REGISTRATION}
        payload.pop("accept_terms")

        response = self.client.post(reverse("portal_register"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Company.objects.filter(name="New Fleet Rentals").exists())

    def test_a_bounced_submission_reopens_on_the_step_that_failed(self):
        response = self.client.post(
            reverse("portal_register"), {**REGISTRATION, "password2": "mismatch"}
        )
        self.assertEqual(response.context["step"], 1)

        response = self.client.post(
            reverse("portal_register"), {**REGISTRATION, "business_name": ""}
        )
        self.assertEqual(response.context["step"], 2)


class AuthPageTests(TestCase):
    """The pages that lead into the portal."""

    def test_the_portal_login_offers_registration(self):
        response = self.client.get(reverse("portal_login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome")
        self.assertContains(response, reverse("portal_register"))

    def test_the_registration_wizard_renders_both_steps(self):
        response = self.client.get(reverse("portal_register"))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Personal Information", body)
        self.assertIn("Business Information", body)
        self.assertIn('data-pane="1"', body)
        self.assertIn('data-pane="2"', body)

    def test_an_authenticated_owner_is_sent_on_rather_than_shown_the_form(self):
        company = make_company("Already Rentals", contract_signed=False)
        self.client.force_login(company.owner)

        response = self.client.get(reverse("portal_register"))
        self.assertRedirects(response, reverse("company_contract"))


class GateTests(TestCase):
    """Test 4 — every panel route refuses an unsigned company."""

    def setUp(self):
        self.company = make_company("Unsigned Rentals", contract_signed=False)
        self.client.force_login(self.company.owner)

    def test_every_panel_page_redirects_to_the_contract(self):
        for name in GUARDED_ROUTES:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(response, reverse("company_contract"))

    def test_a_bookmarked_detail_url_is_refused_too(self):
        car = make_car(self.company)
        response = self.client.get(reverse("company_car_edit", args=[car.pk]))
        self.assertRedirects(response, reverse("company_contract"))

    def test_a_write_is_refused_as_well_as_a_read(self):
        car = make_car(self.company)
        response = self.client.post(reverse("company_car_toggle", args=[car.pk]))

        self.assertRedirects(response, reverse("company_contract"))
        car.refresh_from_db()
        self.assertTrue(car.is_active)

    def test_report_exports_are_refused(self):
        response = self.client.get(reverse("company_report_export", args=["bookings"]))
        self.assertRedirects(response, reverse("company_contract"))

    def test_signing_out_stays_available(self):
        response = self.client.post(reverse("portal_logout"))
        self.assertRedirects(response, reverse("portal_login"))

    def test_the_public_site_is_unaffected(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cars")).status_code, 200)


class ApiGateTests(TestCase):
    """Test 5 — the same refusal for callers that skip the browser."""

    def setUp(self):
        self.company = make_company("Api Rentals", contract_signed=False)
        self.client.force_login(self.company.owner)

    def test_an_xhr_call_is_refused_with_a_machine_readable_code(self):
        response = self.client.get(
            reverse("company_bookings"), headers={"x-requested-with": "XMLHttpRequest"}
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["code"], "CONTRACT_SIGNATURE_REQUIRED")
        self.assertEqual(payload["contract_url"], reverse("company_contract"))

    def test_a_json_client_is_refused(self):
        response = self.client.get(
            reverse("company_fleet"), headers={"accept": "application/json"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "CONTRACT_SIGNATURE_REQUIRED")

    def test_the_contract_endpoints_stay_open(self):
        response = self.client.get(
            reverse("api_company_contract"),
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "pending_signature")
        self.assertTrue(payload["requires_signature"])
        self.assertIn("Partner Agreement", payload["content"])


class SigningTests(TestCase):
    """Test 2 — signing opens the panel, and is recorded properly."""

    def setUp(self):
        self.company = make_company("Signing Rentals", contract_signed=False)
        self.owner = self.company.owner
        self.owner.first_name = "Elira"
        self.owner.last_name = "Kola"
        self.owner.email = "elira@signing.com"
        self.owner.save()
        self.client.force_login(self.owner)

    def _sign(self, **overrides):
        payload = {"signature_name": "Elira Kola", "accept_terms": "on"}
        payload.update(overrides)
        return self.client.post(reverse("company_contract_sign"), payload)

    def test_signing_records_the_full_signature_and_opens_the_dashboard(self):
        response = self._sign(HTTP_USER_AGENT="Mozilla/5.0 Test")

        self.assertRedirects(response, reverse("company_dashboard"))

        contract = current_contract(self.company)
        self.assertEqual(contract.status, CompanyContract.Status.SIGNED)
        self.assertEqual(contract.signed_by, self.owner)
        self.assertEqual(contract.signer_name, "Elira Kola")
        self.assertEqual(contract.signer_email, "elira@signing.com")
        self.assertEqual(contract.signature_name, "Elira Kola")
        self.assertIsNotNone(contract.signed_at)
        self.assertEqual(len(contract.signature_hash), 64)
        self.assertTrue(contract.content_matches_hash)

        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 200)

    def test_the_dashboard_reports_the_signed_state(self):
        self._sign()
        body = self.client.get(reverse("company_dashboard")).content.decode()

        self.assertIn("Contract Status", body)
        self.assertIn("Signed", body)
        self.assertIn("Elira Kola", body)

    def test_signing_is_audited(self):
        self._sign()

        entry = AuditLog.objects.filter(action=AuditLog.Action.CONTRACT_SIGNED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.company, self.company)
        self.assertEqual(entry.metadata["signer"], "Elira Kola")
        self.assertEqual(
            entry.metadata["signature_hash"], current_contract(self.company).signature_hash
        )

    def test_opening_the_contract_is_audited_once(self):
        self.client.get(reverse("company_contract"))
        self.client.get(reverse("company_contract"))

        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.CONTRACT_VIEWED).count(), 1
        )

    def test_without_the_acknowledgement_nothing_is_signed(self):
        response = self._sign(accept_terms="")

        self.assertRedirects(response, reverse("company_contract"))
        self.assertTrue(current_contract(self.company).is_pending)

    def test_a_signature_needs_a_real_name(self):
        response = self._sign(signature_name="  ")

        self.assertRedirects(response, reverse("company_contract"))
        self.assertTrue(current_contract(self.company).is_pending)

    def test_signing_twice_changes_nothing(self):
        self._sign()
        first = current_contract(self.company)

        self._sign(signature_name="Someone Else")

        second = current_contract(self.company)
        self.assertEqual(second.signature_name, first.signature_name)
        self.assertEqual(second.signed_at, first.signed_at)

    def test_the_api_can_sign_too(self):
        response = self.client.post(
            reverse("api_company_contract_sign"),
            data=json.dumps({"signature_name": "Elira Kola", "accept_terms": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["contract"]["status"], "signed")
        self.assertEqual(response.json()["redirect_url"], reverse("company_dashboard"))

    def test_the_api_refuses_to_sign_without_the_acknowledgement(self):
        response = self.client.post(
            reverse("api_company_contract_sign"),
            data=json.dumps({"signature_name": "Elira Kola"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(current_contract(self.company).is_pending)


class SessionTests(TestCase):
    """Test 3 — the decision survives signing out and back in."""

    def test_an_unsigned_company_is_sent_to_the_contract_on_login(self):
        company = make_company("Return Rentals", contract_signed=False)

        response = self.client.post(
            reverse("portal_login"),
            {"username": company.owner.username, "password": PASSWORD},
        )

        self.assertRedirects(response, reverse("company_contract"))

    def test_a_signed_company_lands_on_its_dashboard(self):
        company = make_company("Settled Rentals")

        response = self.client.post(
            reverse("portal_login"),
            {"username": company.owner.username, "password": PASSWORD},
        )

        self.assertRedirects(response, reverse("company_dashboard"))
        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 200)

    def test_a_next_parameter_cannot_step_around_the_gate(self):
        company = make_company("Sneaky Rentals", contract_signed=False)

        response = self.client.post(
            reverse("portal_login") + f"?next={reverse('company_fleet')}",
            {"username": company.owner.username, "password": PASSWORD},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[-1][0], reverse("company_contract"))


class SecurityTests(TestCase):
    """What a company must not be able to do to a contract — its own or anyone's."""

    def setUp(self):
        self.company = make_company("Alpha Rentals", contract_signed=False)
        self.other = make_company("Beta Rentals", contract_signed=False)
        self.client.force_login(self.company.owner)

    def test_a_company_cannot_open_another_companys_contract(self):
        contract = current_contract(self.other)

        response = self.client.get(
            reverse("company_contract_detail", args=[contract.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_a_company_cannot_read_another_companys_contract_over_the_api(self):
        contract = current_contract(self.other)

        response = self.client.get(
            reverse("api_company_contract_detail", args=[contract.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_posted_status_fields_are_ignored(self):
        self.client.post(
            reverse("company_contract_sign"),
            {
                "signature_name": "Test Owner",
                "accept_terms": "on",
                # None of this is read by the server.
                "status": "signed",
                "version": "9.9",
                "signed_at": "2020-01-01T00:00:00Z",
                "signer_name": "Someone Else",
                "signature_hash": "0" * 64,
                "content": "I owe nothing.",
            },
        )

        contract = current_contract(self.company)
        template = contract_service.active_template()
        self.assertEqual(contract.version, template.version)
        self.assertEqual(contract.content, template.body)
        self.assertEqual(contract.signer_name, self.company.owner.get_full_name())
        self.assertNotEqual(contract.signature_hash, "0" * 64)

    def test_a_signed_contract_cannot_be_rewritten(self):
        contract = sign_contract(current_contract(self.company))

        contract = CompanyContract.objects.get(pk=contract.pk)
        contract.content = "Tampered."

        with self.assertRaises(ContractImmutable):
            contract.save()

    def test_a_signed_contract_cannot_be_unsigned(self):
        contract = sign_contract(current_contract(self.company))

        contract = CompanyContract.objects.get(pk=contract.pk)
        contract.status = CompanyContract.Status.PENDING_SIGNATURE

        with self.assertRaises(ContractImmutable):
            contract.save()

    def test_a_signed_contract_cannot_be_deleted(self):
        contract = sign_contract(current_contract(self.company))

        with self.assertRaises(ContractImmutable):
            CompanyContract.objects.get(pk=contract.pk).delete()

    def test_a_signed_template_cannot_be_edited(self):
        sign_contract(current_contract(self.company))

        template = ContractTemplate.objects.get(pk=contract_service.active_template().pk)
        template.body = "Shorter terms."

        with self.assertRaises(ContractImmutable):
            template.save()

    def test_an_anonymous_visitor_cannot_read_a_contract(self):
        self.client.logout()

        response = self.client.get(reverse("api_company_contract"))
        self.assertEqual(response.status_code, 401)

    def test_registration_documents_are_not_public(self):
        from rental.models import CompanyDocument

        document = CompanyDocument.objects.create(
            company=self.other,
            name="licence.pdf",
            content_type="application/pdf",
            size=4,
            data=b"pdf!",
        )

        response = self.client.get(reverse("company_document", args=[document.pk]))
        self.assertEqual(response.status_code, 403)


class VersioningTests(TestCase):
    """Test 7 — a new version locks the panel again until it too is signed."""

    def setUp(self):
        self.company = make_company("Versioned Rentals")
        self.client.force_login(self.company.owner)

    def _publish_v2(self):
        return contract_service.publish_template(
            version="2.0",
            title="Vantage Rentals Partner Agreement",
            body="## 1. Revised terms\n\nThe commission changes.",
        )

    def test_publishing_a_version_reopens_the_gate(self):
        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 200)

        self._publish_v2()

        response = self.client.get(reverse("company_dashboard"))
        self.assertRedirects(response, reverse("company_contract"))

    def test_the_previously_signed_version_is_kept_untouched(self):
        signed = CompanyContract.objects.for_company(self.company).signed().first()
        self._publish_v2()

        signed.refresh_from_db()
        self.assertEqual(signed.status, CompanyContract.Status.SIGNED)
        self.assertEqual(signed.version, "1.0")

        history = CompanyContract.objects.for_company(self.company)
        self.assertEqual(history.count(), 2)

    def test_signing_the_new_version_opens_the_panel_again(self):
        self._publish_v2()

        self.client.post(
            reverse("company_contract_sign"),
            {"signature_name": "Test Owner", "accept_terms": "on"},
        )

        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 200)
        self.assertEqual(
            CompanyContract.objects.for_company(self.company).signed().count(), 2
        )

    def test_an_unsigned_older_version_expires(self):
        pending = make_company("Lapsed Rentals", contract_signed=False)
        old = current_contract(pending)

        self._publish_v2()

        old.refresh_from_db()
        self.assertEqual(old.status, CompanyContract.Status.EXPIRED)

    def test_a_version_number_cannot_be_reused(self):
        self._publish_v2()

        with self.assertRaises(ValidationError):
            self._publish_v2()

    def test_publishing_is_audited(self):
        self._publish_v2()

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.CONTRACT_VERSION_CREATED
            ).exists()
        )


class ConsoleTests(TestCase):
    """Test 6 — what the platform administrator can see."""

    def setUp(self):
        self.signed = make_company("Signed Rentals")
        self.unsigned = make_company("Waiting Rentals", contract_signed=False)
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def test_the_companies_table_shows_a_contract_column(self):
        body = self.client.get(reverse("superadmin_companies")).content.decode()

        self.assertIn("Contract", body)
        self.assertIn("Pending signature", body)
        self.assertIn("Signed", body)

    def test_the_contracts_page_lists_every_contract_with_its_signer(self):
        body = self.client.get(reverse("superadmin_contracts")).content.decode()

        contract = CompanyContract.objects.for_company(self.signed).first()
        self.assertIn(contract.reference, body)
        self.assertIn("Signed Rentals", body)
        self.assertIn(contract.signer_name, body)
        self.assertIn("v1.0", body)

    def test_a_companys_contract_page_shows_the_signature_record(self):
        response = self.client.get(
            reverse("superadmin_company_contract", args=[self.signed.pk])
        )
        body = response.content.decode()
        contract = CompanyContract.objects.for_company(self.signed).first()

        self.assertEqual(response.status_code, 200)
        self.assertIn(contract.reference, body)
        self.assertIn(contract.signature_hash, body)
        self.assertIn(contract.signer_email, body)

    def test_a_pending_company_is_shown_as_pending(self):
        response = self.client.get(
            reverse("superadmin_company_contract", args=[self.unsigned.pk])
        )
        self.assertContains(response, "Pending Signature")

    def test_the_history_api_returns_every_version(self):
        response = self.client.get(
            reverse("api_console_company_contracts", args=[self.signed.pk])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["company"]["name"], "Signed Rentals")
        self.assertEqual(payload["contracts"][0]["status"], "signed")
        self.assertEqual(payload["contracts"][0]["signer"]["name"], "Test Owner")

    def test_the_console_is_not_gated_by_a_companys_contract(self):
        # The administrator has no company of their own; drilling into an
        # unsigned one must stay possible.
        self.client.get(reverse("superadmin_company_enter", args=[self.unsigned.pk]))

        response = self.client.get(reverse("company_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_an_administrator_cannot_sign_for_a_company(self):
        self.client.get(reverse("superadmin_company_enter", args=[self.unsigned.pk]))

        response = self.client.post(
            reverse("company_contract_sign"),
            {"signature_name": "Platform Admin", "accept_terms": "on"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(current_contract(self.unsigned).is_pending)

    def test_a_company_cannot_reach_the_console_contract_pages(self):
        self.client.force_login(self.signed.owner)

        response = self.client.get(
            reverse("superadmin_company_contract", args=[self.unsigned.pk])
        )
        self.assertEqual(response.status_code, 403)


class ContractTextTests(TestCase):
    def test_headings_and_paragraphs_are_split_for_rendering(self):
        sections = contract_service.contract_sections(
            "Intro line.\n\n## 1. Scope\n\nFirst clause.\nStill first clause.\n\nSecond."
        )

        self.assertEqual(sections[0]["heading"], None)
        self.assertEqual(sections[0]["paragraphs"], ["Intro line."])
        self.assertEqual(sections[1]["heading"], "1. Scope")
        self.assertEqual(
            sections[1]["paragraphs"], ["First clause. Still first clause.", "Second."]
        )

    def test_a_company_without_a_contract_is_issued_one_on_demand(self):
        company = make_company("Legacy Rentals", contract_signed=False)
        CompanyContract.objects.filter(company=company).delete()

        self.assertTrue(contract_service.requires_signature(company))
        self.assertIsNotNone(current_contract(company))

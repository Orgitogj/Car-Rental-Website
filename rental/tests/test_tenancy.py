from django.test import TestCase
from django.urls import reverse
from rental.access import SESSION_KEY
from rental.models import AuditLog, Booking, Car, Company, Extra, MaintenanceRecord
from rental.tests.factories import (
    future,
    make_booking,
    make_car,
    make_company,
    make_extra,
    make_superuser,
)

class TenantIsolationTests(TestCase):

    def setUp(self):
        self.company_a = make_company("Alpha Rentals")
        self.company_b = make_company("Beta Rentals")

        self.car_a = make_car(self.company_a, name="A-Car")
        self.car_b = make_car(self.company_b, name="B-Car")

        self.booking_b = make_booking(self.car_b, status=Booking.Status.PENDING)

        self.client.force_login(self.company_a.owner)

    def test_fleet_page_shows_only_own_vehicles(self):
        response = self.client.get(reverse("company_fleet"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A-Car")
        self.assertNotContains(response, "B-Car")

    def test_bookings_page_shows_only_own_bookings(self):
        response = self.client.get(reverse("company_bookings"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.booking_b.reference)

    def test_cannot_confirm_another_companys_booking(self):
        response = self.client.post(
            reverse("company_booking_confirm", args=[self.booking_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.booking_b.refresh_from_db()
        self.assertEqual(self.booking_b.status, Booking.Status.PENDING)

    def test_cannot_cancel_another_companys_booking(self):
        response = self.client.post(
            reverse("company_booking_cancel", args=[self.booking_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.booking_b.refresh_from_db()
        self.assertEqual(self.booking_b.status, Booking.Status.PENDING)

    def test_cannot_edit_another_companys_vehicle(self):
        response = self.client.get(reverse("company_car_edit", args=[self.car_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_companys_vehicle(self):
        response = self.client.post(reverse("company_car_delete", args=[self.car_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Car.objects.filter(pk=self.car_b.pk).exists())

    def test_bulk_update_ignores_other_companies_ids(self):
        self.client.post(
            reverse("company_bookings_bulk"),
            {"booking_ids": [self.booking_b.pk], "action": "confirm"},
        )
        self.booking_b.refresh_from_db()
        self.assertEqual(self.booking_b.status, Booking.Status.PENDING)

    def test_export_contains_only_own_data(self):
        make_booking(self.car_a, status=Booking.Status.CONFIRMED)
        response = self.client.get(reverse("company_report_export", args=["bookings"]))
        self.assertEqual(response.status_code, 200)

        body = response.content
        self.assertNotIn(self.booking_b.reference.encode(), body)

    def test_company_query_parameter_cannot_widen_an_export(self):
        response = self.client.get(
            reverse("company_report_export", args=["bookings"]),
            {"company": self.company_b.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.booking_b.reference.encode(), response.content)

    def test_platform_console_is_refused(self):
        response = self.client.get(reverse("superadmin_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_platform_export_is_refused(self):
        response = self.client.get(
            reverse("superadmin_report_export", args=["companies"])
        )
        self.assertEqual(response.status_code, 403)


class CompanyProfileIsOwnersTests(TestCase):
    """A company's profile is the company's, even from the platform console."""

    def setUp(self):
        self.company = make_company("Epsilon Rentals")
        self.root = make_superuser()
        self.client.force_login(self.root)

    def _profile_payload(self, name):
        return {
            "name": name, "email": "x@example.com", "phone": "", "city": "",
            "address": "", "website": "", "description": "", "status": "active",
        }

    def test_can_read_the_profile(self):
        response = self.client.get(
            reverse("superadmin_company_edit", args=[self.company.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Epsilon Rentals")

    def test_the_save_button_is_rendered_but_inert(self):
        response = self.client.get(
            reverse("superadmin_company_edit", args=[self.company.pk])
        )
        self.assertContains(response, "restricted-action")
        self.assertContains(response, 'aria-disabled="true"')

    def test_cannot_save_the_profile(self):
        original = self.company.name
        response = self.client.post(
            reverse("superadmin_company_edit", args=[self.company.pk]),
            self._profile_payload("Renamed From Console"),
        )
        self.assertEqual(response.status_code, 403)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, original)

    def test_the_blocked_save_is_audited(self):
        self.client.post(
            reverse("superadmin_company_edit", args=[self.company.pk]),
            self._profile_payload("Renamed From Console"),
        )
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    # -- platform-level actions must survive --------------------------------

    def test_can_still_create_a_company(self):
        response = self.client.post(
            reverse("superadmin_company_create"),
            {
                "name": "Brand New Rentals", "email": "new@example.com",
                "phone": "", "city": "", "address": "", "website": "",
                "description": "", "status": "active",
                "owner_full_name": "New Owner",
                "owner_email": "new-owner@example.com",
                "owner_password": "solid-pass-987",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Company.objects.filter(name="Brand New Rentals").exists())

    def test_can_still_change_company_status(self):
        response = self.client.post(
            reverse("superadmin_company_status", args=[self.company.pk]),
            {"status": Company.Status.SUSPENDED},
        )
        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, Company.Status.SUSPENDED)

    def test_can_still_delete_a_company(self):
        response = self.client.post(
            reverse("superadmin_company_delete", args=[self.company.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())

    def test_the_owner_can_still_edit_their_own_profile(self):
        self.client.force_login(self.company.owner)
        self.client.post(
            reverse("company_settings"), self._profile_payload("Owner Renamed")
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Owner Renamed")


class OwnerIsUnaffectedTests(TestCase):
    """The read-only drill-in must not leak into a company's own console."""

    def setUp(self):
        self.company = make_company("Delta Rentals")
        self.car = make_car(self.company)
        self.booking = make_booking(self.car, status=Booking.Status.PENDING)
        self.client.force_login(self.company.owner)

    def test_no_control_is_marked_restricted(self):
        for name in ["company_dashboard", "company_bookings", "company_fleet"]:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertNotIn("restricted-action", body)

    def test_the_real_mutation_forms_are_rendered(self):
        body = self.client.get(reverse("company_bookings")).content.decode()
        self.assertIn(reverse("company_booking_confirm", args=[self.booking.pk]), body)

    def test_confirming_a_booking_still_works(self):
        self.client.post(reverse("company_booking_confirm", args=[self.booking.pk]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_removing_an_add_on_still_works(self):
        extra = make_extra(self.company)
        self.client.post(reverse("company_extra_delete", args=[extra.pk]))
        self.assertFalse(Extra.objects.filter(pk=extra.pk).exists())

    def test_completing_maintenance_still_works(self):
        record = MaintenanceRecord.objects.create(
            car=self.car,
            company=self.company,
            kind=MaintenanceRecord.Kind.SERVICE,
            scheduled_for=future(3),
        )
        self.client.post(reverse("company_maintenance_complete", args=[record.pk]))
        record.refresh_from_db()
        self.assertEqual(record.status, MaintenanceRecord.Status.COMPLETED)


class ReadOnlyContextTests(TestCase):

    def setUp(self):
        self.company = make_company("Gamma Rentals")
        self.car = make_car(self.company)
        self.booking = make_booking(self.car, status=Booking.Status.PENDING)

        self.root = make_superuser()
        self.client.force_login(self.root)
        self.client.get(reverse("superadmin_company_enter", args=[self.company.pk]))

    def test_entering_sets_the_session_pointer(self):
        self.assertEqual(self.client.session[SESSION_KEY], self.company.pk)

    def test_entering_is_recorded_in_the_audit_log(self):
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.COMPANY_VIEWED, company=self.company
            ).exists()
        )


    def test_can_read_the_dashboard(self):
        response = self.client.get(reverse("company_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gamma Rentals")

    def test_read_only_banner_is_shown(self):
        response = self.client.get(reverse("company_dashboard"))
        self.assertContains(response, "Read-only mode")

    def test_can_read_every_company_page(self):
        for name in [
            "company_dashboard",
            "company_bookings",
            "company_fleet",
            "company_customers",
            "company_pricing",
            "company_maintenance",
            "company_reports",
            "company_settings",
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_can_export_the_companys_data(self):
        response = self.client.get(reverse("company_report_export", args=["bookings"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_cannot_confirm_a_booking(self):
        response = self.client.post(
            reverse("company_booking_confirm", args=[self.booking.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_cannot_cancel_a_booking(self):
        response = self.client.post(
            reverse("company_booking_cancel", args=[self.booking.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_cannot_bulk_update_bookings(self):
        response = self.client.post(
            reverse("company_bookings_bulk"),
            {"booking_ids": [self.booking.pk], "action": "confirm"},
        )
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_cannot_add_a_vehicle(self):
        response = self.client.post(
            reverse("company_car_create"),
            {
                "name": "Sneaky", "brand": "X", "car_type": "suv",
                "price_per_day": "10", "year": 2020, "seats": 4, "doors": 4,
                "bags": 2, "power": 100, "fuel": "petrol", "gear": "manual",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Car.objects.filter(name="Sneaky").exists())

    def test_cannot_edit_a_vehicle(self):
        response = self.client.get(reverse("company_car_edit", args=[self.car.pk]))
        self.assertEqual(response.status_code, 403)

    def test_cannot_delete_a_vehicle(self):
        response = self.client.post(reverse("company_car_delete", args=[self.car.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Car.objects.filter(pk=self.car.pk).exists())

    def test_cannot_unlist_a_vehicle(self):
        response = self.client.post(reverse("company_car_toggle", args=[self.car.pk]))
        self.assertEqual(response.status_code, 403)
        self.car.refresh_from_db()
        self.assertTrue(self.car.is_active)

    def test_cannot_change_company_settings(self):
        original = self.company.name
        response = self.client.post(
            reverse("company_settings"),
            {"name": "Renamed", "email": "x@example.com", "phone": "", "city": "",
             "address": "", "website": "", "description": ""},
        )
        self.assertEqual(response.status_code, 403)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, original)

    def test_cannot_add_pricing_extras(self):
        response = self.client.post(
            reverse("company_pricing"),
            {"name": "Sneaky extra", "price_per_day": "5", "sort_order": 0},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.company.extras.filter(name="Sneaky extra").exists())

    def test_cannot_schedule_maintenance(self):
        response = self.client.post(
            reverse("company_maintenance_create"),
            {"car": self.car.pk, "kind": "service", "scheduled_for": future(3)},
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_remove_a_pricing_extra(self):
        extra = make_extra(self.company)
        response = self.client.post(
            reverse("company_extra_delete", args=[extra.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Extra.objects.filter(pk=extra.pk).exists())

    def test_cannot_complete_maintenance(self):
        record = MaintenanceRecord.objects.create(
            car=self.car,
            company=self.company,
            kind=MaintenanceRecord.Kind.SERVICE,
            scheduled_for=future(3),
        )
        response = self.client.post(
            reverse("company_maintenance_complete", args=[record.pk])
        )
        self.assertEqual(response.status_code, 403)
        record.refresh_from_db()
        self.assertNotEqual(record.status, MaintenanceRecord.Status.COMPLETED)

    def test_scheduling_maintenance_leaves_the_database_alone(self):
        self.client.post(
            reverse("company_maintenance_create"),
            {"car": self.car.pk, "kind": "service", "scheduled_for": future(3)},
        )
        self.assertFalse(MaintenanceRecord.objects.exists())

    def test_mutating_controls_are_rendered_but_inert(self):
        """The button stays on the page; only its behaviour is taken away."""
        for name in ["company_dashboard", "company_bookings", "company_fleet"]:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertIn("restricted-action", body)
                self.assertIn('aria-disabled="true"', body)
                self.assertIn("data-restricted=", body)

    def test_no_mutation_form_is_rendered_in_read_only(self):
        body = self.client.get(reverse("company_bookings")).content.decode()
        self.assertNotIn(
            reverse("company_booking_confirm", args=[self.booking.pk]), body
        )
        self.assertNotIn(
            reverse("company_booking_cancel", args=[self.booking.pk]), body
        )

    def test_blocked_attempts_are_audited(self):
        self.client.post(reverse("company_booking_confirm", args=[self.booking.pk]))
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists()
        )

    def test_read_write_hybrid_views_are_audited_too(self):
        """`pricing` and `settings` write on POST without carrying the decorator."""
        AuditLog.objects.all().delete()

        self.client.post(
            reverse("company_pricing"),
            {"name": "Sneaky", "price_per_day": "5", "sort_order": 0},
        )
        self.client.post(
            reverse("company_settings"),
            {"name": "Renamed", "email": "x@example.com", "phone": "", "city": "",
             "address": "", "website": "", "description": ""},
        )

        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).count(), 2
        )

    def test_exiting_clears_the_context(self):
        self.client.get(reverse("superadmin_company_exit"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 403)

    def test_signing_in_again_does_not_inherit_a_read_only_context(self):
        self.client.logout()
        self.client.post(
            reverse("portal_login"),
            {"username": self.root.username, "password": "test-pass-1234"},
        )
        self.assertNotIn(SESSION_KEY, self.client.session)


class AnonymousAccessTests(TestCase):

    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company)

    def test_company_pages_redirect_to_the_portal_login(self):
        for name in ["company_dashboard", "company_bookings", "company_fleet"]:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/portal/login/", response["Location"])

    def test_console_pages_redirect_to_the_portal_login(self):
        response = self.client.get(reverse("superadmin_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/portal/login/", response["Location"])

    def test_customer_cannot_reach_the_company_console(self):
        from django.contrib.auth.models import User

        customer = User.objects.create_user(
            username="cust@example.com", password="test-pass-1234"
        )
        self.client.force_login(customer)
        self.assertEqual(self.client.get(reverse("company_dashboard")).status_code, 403)

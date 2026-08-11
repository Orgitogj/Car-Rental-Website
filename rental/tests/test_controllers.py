import json
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from rental.models import Booking, ContactMessage
from rental.tests.factories import future, make_car, make_company, make_extra, make_superuser

class PublicPageTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company)

    def test_every_public_page_renders(self):
        pages = [
            reverse("home"),
            reverse("cars"),
            reverse("car_detail", args=[self.car.pk]),
            reverse("about"),
            reverse("how_it_works"),
            reverse("functionalities"),
            reverse("contact"),
            reverse("booking_lookup"),
            reverse("login"),
            reverse("register"),
            reverse("portal_login"),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_navbar_offers_login_signup_and_the_company_portal_when_signed_out(self):
        body = self.client.get(reverse("home")).content.decode()

        self.assertIn('class="nav-action"', body)
        self.assertIn(reverse("login"), body)
        self.assertIn(reverse("register"), body)
        self.assertIn('class="btn-companies"', body)
        self.assertIn(reverse("portal_login"), body)

    def test_navbar_swaps_those_for_the_account_menu_once_signed_in(self):
        self.client.force_login(self.company.owner)
        body = self.client.get(reverse("home")).content.decode()

        self.assertIn('class="user-btn"', body)
        self.assertNotIn('class="btn-companies"', body)
        self.assertNotIn('class="nav-action"', body)

    def test_language_pill_marks_the_active_language(self):
        body = self.client.get(reverse("home")).content.decode()

        self.assertIn('class="lang__code"', body)
        self.assertIn('aria-current="true"', body)

    def test_how_it_works_renders_without_any_vehicle_imagery(self):
        # The fixture car has no images; the page must still render.
        response = self.client.get(reverse("how_it_works"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["hero_car"])
        self.assertContains(response, "hiw__arch-fallback")

    def test_how_it_works_hero_uses_a_real_bookable_vehicle(self):
        from rental.models import CarImage

        CarImage.objects.create(car=self.car, image=b"fake-bytes", is_main=True)

        response = self.client.get(reverse("how_it_works"))
        self.assertEqual(response.context["hero_car"], self.car)
        self.assertContains(response, self.car.main_image.url)

    def test_how_it_works_hero_ignores_vehicles_that_are_not_bookable(self):
        from rental.models import CarImage

        CarImage.objects.create(car=self.car, image=b"fake-bytes", is_main=True)
        self.car.is_active = False
        self.car.save(update_fields=["is_active"])

        self.assertIsNone(self.client.get(reverse("how_it_works")).context["hero_car"])

    def test_functionalities_counts_come_from_the_database(self):
        make_car(self.company, name="Panda", brand="Fiat")
        response = self.client.get(reverse("functionalities"))

        stats = response.context["stats"]
        self.assertEqual(stats["vehicles"], 2)
        self.assertEqual(stats["companies"], 1)
        self.assertEqual(stats["bookings"], 0)

    def test_functionalities_counts_a_vehicle_out_today_as_unavailable(self):
        from rental.tests.factories import make_booking

        make_booking(self.car, start_offset=0, days=4)

        stats = self.client.get(reverse("functionalities")).context["stats"]
        self.assertEqual(stats["vehicles"], 1)
        self.assertEqual(stats["available"], 0)
        self.assertEqual(stats["bookings"], 1)

    def test_functionalities_cta_prefills_the_contact_subject(self):
        response = self.client.get(reverse("functionalities"))
        self.assertContains(response, reverse("contact") + "?subject=")

    def test_contact_subject_can_be_prefilled_from_the_query_string(self):
        response = self.client.get(reverse("contact"), {"subject": "List my company"})
        self.assertContains(response, 'value="List my company"')

    def test_contact_subject_prefill_is_length_capped(self):
        response = self.client.get(reverse("contact"), {"subject": "x" * 500})
        self.assertEqual(len(response.context["form"].initial["subject"]), 200)

    def test_search_filters_apply(self):
        make_car(self.company, name="Panda", brand="Fiat", car_type="economy", price="20.00")
        response = self.client.get(reverse("cars"), {"type": "economy"})
        self.assertContains(response, "Panda")
        self.assertNotContains(response, "X5")

    def test_price_filter_applies(self):
        make_car(self.company, name="Panda", brand="Fiat", price="20.00")
        response = self.client.get(reverse("cars"), {"price_max": "25"})
        self.assertContains(response, "Panda")
        self.assertNotContains(response, "X5")

    def test_partial_request_returns_only_the_results_fragment(self):
        response = self.client.get(reverse("cars"), HTTP_X_PARTIAL="results")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!DOCTYPE html>")

    def test_suspended_company_vehicles_are_hidden(self):
        from rental.models import Company

        self.company.status = Company.Status.SUSPENDED
        self.company.save(update_fields=["status"])

        self.assertNotContains(self.client.get(reverse("cars")), "X5")
        self.assertEqual(
            self.client.get(reverse("car_detail", args=[self.car.pk])).status_code, 404
        )

    def test_unlisted_vehicle_is_not_reachable(self):
        self.car.is_active = False
        self.car.save(update_fields=["is_active"])
        self.assertEqual(
            self.client.get(reverse("car_detail", args=[self.car.pk])).status_code, 404
        )

    def test_contact_form_creates_a_message(self):
        response = self.client.post(
            reverse("contact"),
            {
                "full_name": "Ana Test",
                "email": "ana@example.com",
                "subject": "Question",
                "message": "I would like to ask about long-term rentals.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ContactMessage.objects.filter(email="ana@example.com").exists())

    def test_contact_honeypot_rejects_bots(self):
        self.client.post(
            reverse("contact"),
            {
                "full_name": "Bot", "email": "bot@example.com", "subject": "spam",
                "message": "buy things now please", "website": "http://spam.example",
            },
        )
        self.assertFalse(ContactMessage.objects.filter(email="bot@example.com").exists())


class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company, price="45.00")
        self.extra = make_extra(self.company, "GPS", "10.00")

    def test_checkout_redirects_when_dates_are_missing(self):
        response = self.client.get(reverse("checkout", args=[self.car.pk]))
        self.assertEqual(response.status_code, 302)

    def test_checkout_shows_the_quote(self):
        response = self.client.get(
            reverse("checkout", args=[self.car.pk]),
            {"start": future(5), "end": future(8)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "135.00")

    def test_checkout_creates_the_booking(self):
        response = self.client.post(
            reverse("checkout", args=[self.car.pk]),
            {
                "start": future(5), "end": future(8),
                "extras": [self.extra.pk],
                "full_name": "Jane Driver",
                "email": "jane@example.com",
                "phone": "+355691234567",
                "terms": "1",
                "confirm": "1",
            },
        )
        booking = Booking.objects.get(email="jane@example.com")
        self.assertRedirects(
            response, reverse("booking_success", args=[booking.reference])
        )
        self.assertEqual(str(booking.total_price), "165.00")

    def test_checkout_reports_validation_errors(self):
        response = self.client.post(
            reverse("checkout", args=[self.car.pk]),
            {
                "start": future(5), "end": future(8),
                "full_name": "", "email": "not-an-email", "phone": "1",
                "confirm": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.exists())


class BookingApiTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company, price="45.00")
        self.extra = make_extra(self.company, "GPS", "10.00")

    def _post(self, url, payload, client=None):
        return (client or self.client).post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def test_quote_endpoint_returns_pricing(self):
        response = self._post(
            reverse("api_quote"),
            {
                "car_id": self.car.pk,
                "start_date": str(future(5)),
                "end_date": str(future(8)),
                "extras": [self.extra.pk],
            },
        )
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["available"])
        self.assertEqual(data["quote"]["total"], "165.00")

    def test_quote_reports_a_short_stay_without_erroring(self):
        response = self._post(
            reverse("api_quote"),
            {
                "car_id": self.car.pk,
                "start_date": str(future(5)),
                "end_date": str(future(6)),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])

    def test_api_requires_csrf(self):
        enforcing = Client(enforce_csrf_checks=True)
        response = enforcing.post(
            reverse("api_create_booking"),
            data=json.dumps({"car_id": self.car.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_api_rejects_get(self):
        self.assertEqual(self.client.get(reverse("api_quote")).status_code, 405)

    def test_api_does_not_leak_internal_errors(self):
        response = self._post(reverse("api_quote"), {"car_id": None})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.content.decode())


class AuthenticationTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.password = "test-pass-1234"

    def test_login_does_not_reveal_whether_an_account_exists(self):
        unknown = self.client.post(
            reverse("login"),
            {"username": "nobody@example.com", "password": "whatever-1234"},
            follow=True,
        )
        wrong_password = self.client.post(
            reverse("login"),
            {"username": self.company.owner.username, "password": "wrong-pass-1234"},
            follow=True,
        )

        def only_messages(response):
            return sorted(str(m) for m in response.context["messages"])

        self.assertEqual(only_messages(unknown), only_messages(wrong_password))

    def test_company_owner_lands_on_the_dashboard(self):
        response = self.client.post(
            reverse("portal_login"),
            {"username": self.company.owner.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("company_dashboard"))

    def test_superuser_lands_on_the_console(self):
        root = make_superuser()
        response = self.client.post(
            reverse("portal_login"),
            {"username": root.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("superadmin_dashboard"))

    def test_superuser_can_sign_in_with_a_non_email_username(self):
        User.objects.create_superuser(
            username="CarRentalAdmin",
            email="admin@example.com",
            password=self.password,
        )
        response = self.client.post(
            reverse("portal_login"),
            {"username": "CarRentalAdmin", "password": self.password},
        )
        self.assertRedirects(response, reverse("superadmin_dashboard"))

    def test_superuser_can_sign_in_with_their_email_instead(self):
        User.objects.create_superuser(
            username="CarRentalAdmin",
            email="admin@example.com",
            password=self.password,
        )
        response = self.client.post(
            reverse("portal_login"),
            {"username": "ADMIN@example.com", "password": self.password},
        )
        self.assertRedirects(response, reverse("superadmin_dashboard"))

    def test_an_identifier_shared_by_two_accounts_resolves_by_password(self):
        # The owner's username is an address the admin holds as their email.
        shared = self.company.owner.username
        admin = User.objects.create_superuser(
            username="CarRentalAdmin", email=shared, password="admin-pass-5678"
        )

        as_owner = self.client.post(
            reverse("portal_login"), {"username": shared, "password": self.password}
        )
        self.assertRedirects(as_owner, reverse("company_dashboard"))

        self.client.logout()
        as_admin = self.client.post(
            reverse("portal_login"), {"username": shared, "password": "admin-pass-5678"}
        )
        self.assertRedirects(as_admin, reverse("superadmin_dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), admin.pk)

    def test_plain_customer_is_refused_at_the_portal(self):
        User.objects.create_user(username="cust@example.com", password=self.password)
        response = self.client.post(
            reverse("portal_login"),
            {"username": "cust@example.com", "password": self.password},
        )
        self.assertRedirects(response, reverse("portal_login"))

    def test_deactivated_account_cannot_sign_in(self):
        self.company.owner.is_active = False
        self.company.owner.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("portal_login"),
            {"username": self.company.owner.username, "password": self.password},
            follow=True,
        )
        self.assertFalse(response.context["user"].is_authenticated)

    def test_registration_stores_the_phone_number(self):
        self.client.post(
            reverse("register"),
            {
                "full_name": "New Customer",
                "email": "new@example.com",
                "phone": "+355 69 111 2222",
                "password1": "solid-pass-987",
                "password2": "solid-pass-987",
            },
        )
        user = User.objects.get(username="new@example.com")
        self.assertEqual(user.profile.phone, "+355 69 111 2222")

    def test_next_parameter_cannot_redirect_off_site(self):
        response = self.client.post(
            reverse("portal_login") + "?next=https://evil.example/steal",
            {"username": self.company.owner.username, "password": self.password},
        )
        self.assertNotIn("evil.example", response["Location"])


class SuperAdminPageTests(TestCase):
    def setUp(self):
        self.company = make_company()
        make_car(self.company)
        self.root = make_superuser()
        self.client.force_login(self.root)

    def test_every_console_page_renders(self):
        pages = [
            "superadmin_dashboard",
            "superadmin_companies",
            "superadmin_company_create",
            "superadmin_fleet",
            "superadmin_bookings",
            "superadmin_users",
            "superadmin_messages",
            "superadmin_activity",
            "superadmin_reports",
        ]
        for name in pages:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_company_edit_and_delete_pages_render(self):
        self.assertEqual(
            self.client.get(
                reverse("superadmin_company_edit", args=[self.company.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("superadmin_company_delete", args=[self.company.pk])
            ).status_code,
            200,
        )

    def test_global_search_returns_matches(self):
        response = self.client.get(reverse("superadmin_search"), {"q": self.company.name[:5]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["results"])

    def test_global_search_ignores_very_short_queries(self):
        response = self.client.get(reverse("superadmin_search"), {"q": "a"})
        self.assertEqual(response.json()["results"], [])

    def test_suspending_a_company_hides_it_from_the_public_site(self):
        from rental.models import Company

        self.client.post(
            reverse("superadmin_company_status", args=[self.company.pk]),
            {"status": "suspended"},
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, Company.Status.SUSPENDED)

        anonymous = Client()
        self.assertNotContains(anonymous.get(reverse("cars")), "X5")

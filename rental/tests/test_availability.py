from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rental.models import Booking, Company
from rental.services import bookings as booking_service
from rental.tests.factories import (
    future,
    make_booking,
    make_car,
    make_company,
)
class OccupiedNightsTests(TestCase):
    def setUp(self):
        self.company = make_company("Calendar Rentals")
        self.car = make_car(self.company)

    def test_a_booking_blocks_its_nights_but_not_its_return_day(self):
        # Days 5, 6, 7 are slept on; the car is handed back on day 8.
        make_booking(self.car, start_offset=5, days=3)

        nights = booking_service.occupied_nights(self.car)

        self.assertEqual(nights, [future(5), future(6), future(7)])
        self.assertNotIn(future(8), nights)

    def test_the_blocked_set_matches_what_booking_creation_refuses(self):
        make_booking(self.car, start_offset=5, days=3)
        nights = set(booking_service.occupied_nights(self.car))

        for offset in range(4, 10):
            day = future(offset)
            single_night_is_free = booking_service.is_available(
                self.car, day, day + timedelta(days=1)
            )
            self.assertEqual(
                single_night_is_free,
                day not in nights,
                f"calendar and validator disagree about {day}",
            )

    def test_several_bookings_are_all_reflected(self):
        make_booking(self.car, start_offset=5, days=3)
        make_booking(self.car, start_offset=15, days=5)

        nights = booking_service.occupied_nights(self.car)

        self.assertEqual(
            nights,
            [future(n) for n in (5, 6, 7, 15, 16, 17, 18, 19)],
        )

    def test_pending_bookings_hold_the_vehicle_too(self):
        make_booking(self.car, start_offset=5, days=2, status=Booking.Status.PENDING)
        self.assertIn(future(5), booking_service.occupied_nights(self.car))

    def test_cancelled_bookings_release_their_nights(self):
        make_booking(self.car, start_offset=5, days=2, status=Booking.Status.CANCELLED)
        self.assertEqual(booking_service.occupied_nights(self.car), [])

    def test_another_vehicles_bookings_are_not_counted(self):
        other = make_car(self.company, name="Other")
        make_booking(other, start_offset=5, days=3)
        self.assertEqual(booking_service.occupied_nights(self.car), [])

    def test_bookings_already_under_way_are_clipped_to_today(self):
        today = timezone.localdate()
        Booking.objects.create(
            car=self.car,
            company=self.company,
            full_name="Early Bird",
            email="early@example.com",
            phone="+355690000000",
            start_date=today - timedelta(days=4),
            end_date=today + timedelta(days=2),
            days=6,
            price_per_day=self.car.price_per_day,
            base_total=0,
            total_price=0,
            status=Booking.Status.CONFIRMED,
        )

        nights = booking_service.occupied_nights(self.car)

        self.assertEqual(nights, [today, today + timedelta(days=1)])

    def test_bookings_beyond_the_window_are_left_out(self):
        make_booking(self.car, start_offset=400, days=3)
        self.assertEqual(booking_service.occupied_nights(self.car), [])


class AvailabilityEndpointTests(TestCase):
    def setUp(self):
        self.company = make_company("Endpoint Rentals")
        self.car = make_car(self.company)

    def url(self, car=None):
        return reverse("api_availability", args=[(car or self.car).pk])

    def test_returns_the_blocked_days_for_the_vehicle(self):
        make_booking(self.car, start_offset=5, days=3)

        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(
            payload["unavailable"],
            [future(n).isoformat() for n in (5, 6, 7)],
        )
        self.assertEqual(payload["car_id"], self.car.pk)
        self.assertEqual(payload["today"], timezone.localdate().isoformat())
        self.assertIn("min_days", payload)

    def test_is_open_to_visitors_who_are_not_signed_in(self):
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_it_leaks_nothing_about_who_booked(self):
        booking = make_booking(self.car, start_offset=5, days=3)
        body = self.client.get(self.url()).content

        self.assertNotIn(booking.reference.encode(), body)
        self.assertNotIn(booking.full_name.encode(), body)
        self.assertNotIn(booking.email.encode(), body)

    def test_an_inactive_vehicle_has_no_calendar(self):
        self.car.is_active = False
        self.car.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_a_suspended_companys_vehicle_has_no_calendar(self):
        self.company.status = Company.Status.SUSPENDED
        self.company.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_it_refuses_to_be_written_to(self):
        self.assertEqual(self.client.post(self.url()).status_code, 405)


class CalendarAndCheckoutAgreeTests(TestCase):

    def setUp(self):
        self.company = make_company("Gap Rentals")
        self.car = make_car(self.company)
        make_booking(self.car, start_offset=5, days=3)   # nights 5,6,7
        make_booking(self.car, start_offset=15, days=5)  # nights 15..19

    def test_the_whole_gap_between_two_bookings_can_be_booked(self):
        # Return day 15 is the first blocked night — allowed as a hand-back.
        self.assertTrue(
            booking_service.is_available(self.car, future(8), future(15))
        )

    def test_a_range_that_spans_a_booking_is_refused(self):
        self.assertFalse(
            booking_service.is_available(self.car, future(8), future(16))
        )

    def test_collecting_on_a_booked_night_is_refused(self):
        self.assertFalse(
            booking_service.is_available(self.car, future(6), future(9))
        )

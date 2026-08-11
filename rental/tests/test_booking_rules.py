from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from rental.models import Booking, BookingExtra
from rental.services import bookings as service
from rental.services.bookings import BookingError
from rental.tests.factories import future, make_booking, make_car, make_company, make_extra

class AvailabilityTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company)

    def test_overlapping_booking_blocks_the_dates(self):
        make_booking(self.car, start_offset=10, days=4)  # 10 -> 14
        self.assertFalse(service.is_available(self.car, future(11), future(13)))

    def test_same_day_turnover_is_allowed(self):
        
        make_booking(self.car, start_offset=10, days=4)  # ends day 14
        self.assertTrue(service.is_available(self.car, future(14), future(17)))

    def test_search_and_booking_agree_on_availability(self):
        
        make_booking(self.car, start_offset=10, days=4)
        start, end = future(11), future(13)

        from rental.models import Car

        in_search = Car.objects.filter(pk=self.car.pk).available_between(start, end).exists()
        bookable = service.is_available(self.car, start, end)

        self.assertEqual(in_search, bookable)
        self.assertFalse(bookable)

    def test_cancelled_bookings_do_not_block(self):
        make_booking(self.car, start_offset=10, days=4, status=Booking.Status.CANCELLED)
        self.assertTrue(service.is_available(self.car, future(11), future(13)))

    def test_pending_bookings_do_block(self):
        make_booking(self.car, start_offset=10, days=4, status=Booking.Status.PENDING)
        self.assertFalse(service.is_available(self.car, future(11), future(13)))


class QuoteTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company, price="45.00")
        self.extra = make_extra(self.company, "GPS", "10.00")

    def test_quote_totals(self):
        quote = service.build_quote(self.car, future(3), future(6))  # 3 days
        self.assertEqual(quote.days, 3)
        self.assertEqual(quote.base_total, Decimal("135.00"))
        self.assertEqual(quote.total, Decimal("135.00"))

    def test_extras_are_priced_per_day_from_the_database(self):
        quote = service.build_quote(self.car, future(3), future(6), [self.extra.pk])
        self.assertEqual(quote.extras_total, Decimal("30.00"))
        self.assertEqual(quote.total, Decimal("165.00"))

    def test_extras_from_another_company_are_ignored(self):
        other = make_company("Other Rentals")
        foreign = make_extra(other, "Foreign extra", "999.00")

        quote = service.build_quote(self.car, future(3), future(6), [foreign.pk])
        self.assertEqual(quote.extras_total, Decimal("0.00"))
        self.assertEqual(quote.total, Decimal("135.00"))

    def test_rejects_stay_shorter_than_the_minimum(self):
        with self.assertRaises(BookingError):
            service.build_quote(self.car, future(3), future(4))

    def test_rejects_dates_in_the_past(self):
        with self.assertRaises(BookingError):
            service.build_quote(self.car, future(-2), future(3))

    def test_rejects_reversed_range(self):
        with self.assertRaises(BookingError):
            service.build_quote(self.car, future(9), future(3))


class CreateBookingTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.car = make_car(self.company, price="45.00")
        self.extra = make_extra(self.company, "GPS", "10.00")

    def _create(self, **overrides):
        payload = {
            "car_id": self.car.pk,
            "full_name": "Jane Driver",
            "email": "Jane@Example.com",
            "phone": "+355 69 123 4567",
            "start_date": future(5),
            "end_date": future(8),
        }
        payload.update(overrides)
        return service.create_booking(**payload)

    def test_creates_booking_with_stored_pricing(self):
        booking = self._create()
        self.assertEqual(booking.days, 3)
        self.assertEqual(booking.total_price, Decimal("135.00"))
        self.assertEqual(booking.company, self.company)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertTrue(booking.reference.startswith("CR-"))

    def test_extras_are_persisted_as_line_items(self):
        booking = self._create(extra_ids=[self.extra.pk])
        self.assertEqual(booking.extras_total, Decimal("30.00"))
        self.assertEqual(booking.total_price, Decimal("165.00"))

        line = BookingExtra.objects.get(booking=booking)
        self.assertEqual(line.name, "GPS")
        self.assertEqual(line.total, Decimal("30.00"))

    def test_creates_the_customer_record(self):
        booking = self._create()
        self.assertIsNotNone(booking.customer)
        self.assertEqual(booking.customer.email, "jane@example.com")

    def test_repeat_booking_reuses_the_customer(self):
        first = self._create()
        second = self._create(start_date=future(20), end_date=future(24))
        self.assertEqual(first.customer_id, second.customer_id)

    def test_double_booking_is_refused(self):
        self._create()
        with self.assertRaises(BookingError) as ctx:
            self._create()
        self.assertEqual(ctx.exception.code, "unavailable")

    def test_cannot_book_an_unlisted_vehicle(self):
        self.car.is_active = False
        self.car.save(update_fields=["is_active"])
        with self.assertRaises(BookingError):
            self._create()

    def test_cannot_book_from_a_suspended_company(self):
        from rental.models import Company

        self.company.status = Company.Status.SUSPENDED
        self.company.save(update_fields=["status"])
        with self.assertRaises(BookingError) as ctx:
            self._create()
        self.assertEqual(ctx.exception.code, "company_inactive")

    def test_missing_contact_details_are_refused(self):
        with self.assertRaises(BookingError):
            self._create(full_name="", email="", phone="")

    def test_booking_increments_vehicle_popularity(self):
        before = self.car.popularity
        self._create()
        self.car.refresh_from_db()
        self.assertEqual(self.car.popularity, before + 1)

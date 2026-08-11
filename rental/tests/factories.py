from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.utils import timezone
from rental.models import Booking, Car, Company, CompanyContract, Extra
from rental.services import contracts as contract_service


def make_company(
    name="Acme Rentals",
    *,
    status=Company.Status.ACTIVE,
    owner=None,
    contract_signed=True,
):
    """An established company: on the platform, with its contract signed.

    `contract_signed=False` leaves it at the onboarding gate, which is what a
    company looks like the moment it registers.
    """
    if owner is None:
        owner = User.objects.create_user(
            username=f"owner-{name.lower().replace(' ', '-')}@example.com",
            email=f"owner-{name.lower().replace(' ', '-')}@example.com",
            password="test-pass-1234",
            first_name="Test",
            last_name="Owner",
        )
    company = Company.objects.create(
        name=name,
        email=f"hello@{name.lower().replace(' ', '')}.com",
        owner=owner,
        status=status,
        city="Tirana",
    )

    contract = contract_service.issue_contract(company)
    if contract_signed:
        sign_contract(contract, user=owner)

    return company


def sign_contract(contract, *, user=None, signature_name="Test Owner"):
    return contract_service.sign_contract(
        contract,
        user=user or contract.company.owner,
        signature_name=signature_name,
    )


def current_contract(company):
    return CompanyContract.objects.for_company(company).first()


def make_car(company, name="X5", brand="BMW", price="45.00", **kwargs):
    defaults = {
        "car_type": Car.Category.SUV,
        "year": 2022,
        "seats": 5,
        "power": 250,
        "fuel": Car.Fuel.DIESEL,
        "gear": Car.Gear.AUTOMATIC,
        "is_active": True,
    }
    defaults.update(kwargs)
    return Car.objects.create(
        company=company,
        name=name,
        brand=brand,
        price_per_day=Decimal(price),
        **defaults,
    )


def make_extra(company, name="GPS", price="10.00"):
    return Extra.objects.create(
        company=company, name=name, price_per_day=Decimal(price)
    )


def make_booking(car, *, start_offset=5, days=3, status=Booking.Status.CONFIRMED):
    start = timezone.localdate() + timedelta(days=start_offset)
    end = start + timedelta(days=days)
    return Booking.objects.create(
        car=car,
        company=car.company,
        full_name="Test Customer",
        email="customer@example.com",
        phone="+355691234567",
        start_date=start,
        end_date=end,
        days=days,
        price_per_day=car.price_per_day,
        base_total=car.price_per_day * days,
        total_price=car.price_per_day * days,
        status=status,
    )


def make_superuser(username="root@example.com"):
    return User.objects.create_superuser(
        username=username, email=username, password="test-pass-1234"
    )


def future(days_from_now):
    return timezone.localdate() + timedelta(days=days_from_now)

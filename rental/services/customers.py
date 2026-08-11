from django.db import IntegrityError, transaction
from django.utils import timezone
from ..models import Customer


def upsert_customer(*, company, full_name, email, phone=""):
    
    email = (email or "").strip().lower()
    if not email:
        return None

    customer = Customer.objects.filter(company=company, email=email).first()

    if customer is None:
        try:
            with transaction.atomic():
                customer = Customer.objects.create(
                    company=company,
                    email=email,
                    full_name=full_name.strip(),
                    phone=phone.strip(),
                    last_booked_at=timezone.now(),
                )
            return customer
        except IntegrityError:
           
            customer = Customer.objects.filter(company=company, email=email).first()
            if customer is None:
                raise

    updates = ["last_booked_at"]
    customer.last_booked_at = timezone.now()

    if full_name and full_name.strip() != customer.full_name:
        customer.full_name = full_name.strip()
        updates.append("full_name")
    if phone and phone.strip() != customer.phone:
        customer.phone = phone.strip()
        updates.append("phone")

    customer.save(update_fields=updates)
    return customer

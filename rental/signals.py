import logging
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext as _

from .models import Booking

logger = logging.getLogger("rental.signals")


@receiver(pre_save, sender=Booking)
def remember_previous_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = (
        Booking.objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=Booking)
def send_confirmation_email(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_status", None)

    if created or previous == instance.status:
        return
    if instance.status != Booking.Status.CONFIRMED:
        return

    transaction.on_commit(lambda: _deliver(instance.pk))


def _deliver(booking_pk):
    from django.core.mail import EmailMessage

    booking = (
        Booking.objects.select_related("car", "company").filter(pk=booking_pk).first()
    )
    if booking is None:
        return

    body = _(
        "Hello %(name)s,\n\n"
        "Good news — your booking is confirmed.\n\n"
        "Reference: %(ref)s\n"
        "Vehicle: %(car)s\n"
        "Pick-up: %(start)s\n"
        "Return: %(end)s\n"
        "Total: %(currency)s%(total)s\n\n"
        "We look forward to seeing you.\n"
        "%(company)s"
    ) % {
        "name": booking.full_name,
        "ref": booking.reference,
        "car": booking.car.title,
        "start": booking.start_date,
        "end": booking.end_date,
        "currency": settings.DEFAULT_CURRENCY_SYMBOL,
        "total": booking.total_price,
        "company": booking.company.name,
    }

    try:
        EmailMessage(
            subject=_("Booking confirmed – %(ref)s") % {"ref": booking.reference},
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.email],
        ).send(fail_silently=True)
    except Exception:  # pragma: no cover
        logger.exception("Confirmation email failed for %s", booking.reference)

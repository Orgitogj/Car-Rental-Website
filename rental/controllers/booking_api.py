import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from ..models import Car, Company
from ..services import bookings as booking_service
from ..services.bookings import BookingError


def _payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or "{}")
        except (ValueError, UnicodeDecodeError):
            return None
    return request.POST.dict()


def _bookable_car(car_id):
    return get_object_or_404(
        Car.objects.select_related("company"),
        pk=car_id,
        is_active=True,
        company__status=Company.Status.ACTIVE,
    )


@require_GET
def availability(request, car_id):
    car = _bookable_car(car_id)
    return JsonResponse(booking_service.availability_window(car))


@require_POST
def quote(request):

    data = _payload(request)
    if data is None:
        return JsonResponse({"error": _("Malformed request.")}, status=400)

    car_id = data.get("car_id")
    start_date = parse_date(str(data.get("start_date") or ""))
    end_date = parse_date(str(data.get("end_date") or ""))

    if not car_id:
        return JsonResponse({"error": _("Missing vehicle.")}, status=400)

    car = _bookable_car(car_id)

    extra_ids = data.get("extras") or []
    if isinstance(extra_ids, str):
        extra_ids = [extra_ids]

    try:
        result = booking_service.build_quote(car, start_date, end_date, extra_ids)
    except BookingError as exc:
        return JsonResponse(
            {"ok": False, "error": exc.message, "code": exc.code}, status=200
        )

    available = booking_service.is_available(car, start_date, end_date)

    return JsonResponse(
        {
            "ok": True,
            "available": available,
            "quote": result.as_dict(),
            "message": (
                _("Available for your dates")
                if available
                else _("Not available for those dates")
            ),
        }
    )


@require_POST
def create_booking(request):
    data = _payload(request)
    if data is None:
        return JsonResponse({"error": _("Malformed request.")}, status=400)

    extra_ids = data.get("extras") or []
    if isinstance(extra_ids, str):
        extra_ids = [extra_ids]

    try:
        booking = booking_service.create_booking(
            car_id=data.get("car_id"),
            full_name=data.get("full_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            start_date=parse_date(str(data.get("start_date") or "")),
            end_date=parse_date(str(data.get("end_date") or "")),
            extra_ids=extra_ids,
            request=request,
        )
    except BookingError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)

    from django.urls import reverse

    return JsonResponse(
        {
            "ok": True,
            "reference": booking.reference,
            "redirect": reverse("booking_success", args=[booking.reference]),
        }
    )

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from ..access import ensure_can_manage, ensure_same_company
from ..models import AuditLog, Car, CarImage
from . import audit

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/avif"}


def validate_image(upload):
   
    if upload.size > settings.MAX_UPLOAD_IMAGE_BYTES:
        limit_mb = settings.MAX_UPLOAD_IMAGE_BYTES // (1024 * 1024)
        raise ValidationError(
            _("%(file)s is larger than the %(limit)sMB limit.")
            % {"file": upload.name, "limit": limit_mb}
        )

    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(
            _("%(file)s is not a supported image (JPEG, PNG, WebP or AVIF).")
            % {"file": upload.name}
        )
    try:
        from PIL import Image

        upload.seek(0)
        Image.open(upload).verify()
    except Exception as exc:  
        raise ValidationError(
            _("%(file)s could not be read as an image.") % {"file": upload.name}
        ) from exc
    finally:
        upload.seek(0)


@transaction.atomic
def save_car(context, form, request=None, instance=None):
    ensure_can_manage(context, "change vehicles")

    car = form.save(commit=False)

    if instance is not None:
        ensure_same_company(context, instance)
        car.pk = instance.pk

    car.company = context.company
    car.save()

    is_new = instance is None
    audit.record(
        AuditLog.Action.VEHICLE_CREATED if is_new else AuditLog.Action.VEHICLE_UPDATED,
        request=request,
        company=context.company,
        entity=car,
        description=f"{'Added' if is_new else 'Updated'} {car.title}",
    )
    return car


@transaction.atomic
def add_car_images(context, car, uploads, request=None):
    ensure_can_manage(context, "upload photos")
    ensure_same_company(context, car)

    created = []
    has_main = car.images.filter(is_main=True).exists()

    for upload in uploads:
        validate_image(upload)
        image = CarImage.objects.create(
            car=car,
            image=upload.read(),
            image_content_type=(upload.content_type or "image/jpeg").lower(),
            image_name=upload.name[:255],
            is_main=not has_main and not created,
        )
        created.append(image)

    return created


@transaction.atomic
def delete_car_image(context, image, request=None):
    ensure_can_manage(context, "delete photos")
    ensure_same_company(context, image.car)

    was_main = image.is_main
    car = image.car
    image.delete()

    if was_main:
        replacement = car.images.first()
        if replacement:
            replacement.is_main = True
            replacement.save(update_fields=["is_main"])

    return car


@transaction.atomic
def set_main_image(context, image, request=None):
    ensure_can_manage(context, "change photos")
    ensure_same_company(context, image.car)

    CarImage.objects.filter(car=image.car).update(is_main=False)
    image.is_main = True
    image.save(update_fields=["is_main"])
    return image.car


@transaction.atomic
def delete_car(context, car, request=None):
    ensure_can_manage(context, "delete vehicles")
    ensure_same_company(context, car)

    title = car.title
    car_id = car.pk
    car.delete()

    audit.record(
        AuditLog.Action.VEHICLE_DELETED,
        request=request,
        company=context.company,
        entity_type="Car",
        entity_id=car_id,
        description=f"Removed {title}",
    )


@transaction.atomic
def set_car_active(context, car, is_active, request=None):
    ensure_can_manage(context, "change vehicle availability")
    ensure_same_company(context, car)

    car.is_active = is_active
    car.save(update_fields=["is_active", "updated_at"])

    audit.record(
        AuditLog.Action.VEHICLE_UPDATED,
        request=request,
        company=context.company,
        entity=car,
        description=f"{'Listed' if is_active else 'Unlisted'} {car.title}",
    )
    return car

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404
from django.utils.encoding import iri_to_uri
from django.utils.http import http_date, quote_etag
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe
from ..access import own_company
from ..models import CarImage, Company, CompanyDocument


def _image_response(request, data, content_type, last_modified, tag):
    if not data:
        raise Http404("No image")

    payload = bytes(data)
    etag = quote_etag(f"{tag}-{len(payload)}")

    if request.headers.get("If-None-Match") == etag:
        return HttpResponseNotModified()

    response = HttpResponse(payload, content_type=content_type or "image/jpeg")
    response["ETag"] = etag
    response["Content-Length"] = str(len(payload))
    if last_modified:
        response["Last-Modified"] = http_date(last_modified.timestamp())
    response["Cache-Control"] = f"public, max-age={settings.IMAGE_CACHE_SECONDS}"
    return response


@require_safe
@cache_control(public=True)
def car_image(request, image_id):
    image = get_object_or_404(
        CarImage.objects.only(
            "image", "image_content_type", "created_at", "id"
        ),
        pk=image_id,
    )
    return _image_response(
        request,
        image.image,
        image.image_content_type,
        image.created_at,
        f"car-{image.pk}",
    )


@require_safe
def company_document(request, document_id):
    document = get_object_or_404(
        CompanyDocument.objects.select_related("company"), pk=document_id
    )

    user = request.user
    if not user.is_authenticated:
        raise PermissionDenied("Sign in to download this document.")

    own = own_company(user)
    if not user.is_superuser and (own is None or own.pk != document.company_id):
        raise PermissionDenied("This document belongs to a different company.")

    payload = bytes(document.data or b"")
    if not payload:
        raise Http404("No document")

    response = HttpResponse(
        payload, content_type=document.content_type or "application/octet-stream"
    )
    response["Content-Length"] = str(len(payload))
    response["Content-Disposition"] = (
        f'inline; filename*=UTF-8\'\'{iri_to_uri(document.name)}'
    )
    response["Cache-Control"] = "private, max-age=0, no-store"
    return response


@require_safe
@cache_control(public=True)
def company_logo(request, company_id):
    company = get_object_or_404(
        Company.objects.only(
            "logo_data", "logo_content_type", "updated_at", "id"
        ),
        pk=company_id,
    )
    return _image_response(
        request,
        company.logo_data,
        company.logo_content_type,
        company.updated_at,
        f"logo-{company.pk}-{int(company.updated_at.timestamp()) if company.updated_at else 0}",
    )

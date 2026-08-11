"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from rental.controllers import errors

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("", include("rental.accounts.urls")),
    path("", include("rental.urls")),
)

handler400 = errors.bad_request
handler403 = errors.permission_denied
handler404 = errors.not_found
handler500 = errors.server_error

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

import logging
from django.shortcuts import render
logger = logging.getLogger("rental.errors")
def bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)
def permission_denied(request, exception=None):

    detail = str(exception) if exception else ""
    return render(
        request,
        "errors/403.html",
        {"detail": detail if detail and len(detail) < 300 else ""},
        status=403,
    )


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    logger.error("Unhandled server error at %s", request.path)
    return render(request, "errors/500.html", status=500)

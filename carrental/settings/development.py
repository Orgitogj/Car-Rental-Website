"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_list

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,0.0.0.0,192.168.100.3",
)

# Trust the local dev server for CSRF when reached over the LAN.
CSRF_TRUSTED_ORIGINS = [
    f"http://{host}:8000" for host in ALLOWED_HOSTS if host
] + [f"http://{host}" for host in ALLOWED_HOSTS if host]

# Print emails to the console unless real SMTP credentials are configured.
if not env("EMAIL_HOST_PASSWORD", ""):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Surface slow/duplicate queries while developing.
if env_bool("DJANGO_LOG_SQL", False):
    LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }

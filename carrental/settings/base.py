"""
Shared settings for every environment.

Environment-specific modules (development.py / production.py) import * from here
and override what they need. Nothing secret lives in this file: values come from
the environment, loaded from a local .env during development.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv
import os

# carrental/settings/base.py -> carrental/settings -> carrental -> <project root>
BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def env(name, default=None, required=False):
    """Read a setting from the environment."""
    value = os.environ.get(name, default)
    if required and value in (None, ""):
        raise ImproperlyConfigured(
            f"Required environment variable {name!r} is not set. "
            f"Create a .env file in the project root and set it there "
            f"(see the Environment Variables section of the README)."
        )
    return value


def env_bool(name, default=False):
    return str(env(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in str(env(name, default)).split(",") if item.strip()]


# ============================================================================
# CORE
# ============================================================================

SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

ROOT_URLCONF = "carrental.urls"
WSGI_APPLICATION = "carrental.wsgi.application"
ASGI_APPLICATION = "carrental.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = 1

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    "rental.accounts.apps.AccountsConfig",
    "rental.apps.RentalConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "rental.middleware.CompanyContextMiddleware",
    "rental.middleware.ContractGateMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "rental.context_processors.navigation",
                "rental.context_processors.contract_state",
            ],
        },
    },
]

# ============================================================================
# DATABASE
# ============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "SuperRental"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
    }
}

# ============================================================================
# AUTH
# ============================================================================

AUTHENTICATION_BACKENDS = ["rental.accounts.backends.UsernameOrEmailBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# URL names, not paths: i18n_patterns prefixes every path with a language code.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

# ============================================================================
# INTERNATIONALISATION
# ============================================================================

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("sq", _("Shqip")),
    ("en", _("English")),
    ("it", _("Italiano")),
    ("de", _("Deutsch")),
]
LOCALE_PATHS = [BASE_DIR / "rental" / "locale"]
TIME_ZONE = env("DJANGO_TIME_ZONE", "Europe/Tirane")
USE_I18N = True
USE_TZ = True

# ============================================================================
# STATIC / MEDIA
# ============================================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

IMAGE_CACHE_SECONDS = int(env("IMAGE_CACHE_SECONDS", str(60 * 60 * 24 * 30)))

# Reject oversized uploads before they reach the database.
MAX_UPLOAD_IMAGE_BYTES = int(env("MAX_UPLOAD_IMAGE_BYTES", str(5 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ============================================================================
# EMAIL
# ============================================================================

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Car Rental <no-reply@carrental.local>")

# ============================================================================
# BUSINESS RULES
# ============================================================================

MIN_RENTAL_DAYS = int(env("MIN_RENTAL_DAYS", "3"))
DEFAULT_CURRENCY_SYMBOL = env("DEFAULT_CURRENCY_SYMBOL", "€")

# ============================================================================
# CACHING
# ============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "carrental-default",
    }
}

# ============================================================================
# LOGGING
# ============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "rental": {
            "handlers": ["console"],
            "level": env("RENTAL_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}

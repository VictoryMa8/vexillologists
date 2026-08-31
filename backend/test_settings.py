"""Settings used by the automated test suite."""

import os

from .settings import *  # noqa: F403


SECURE_SSL_REDIRECT = False
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("TEST_DB_NAME", "vexillologists"),
        "USER": os.getenv("TEST_DB_USER", "postgres"),
        "PASSWORD": os.getenv("TEST_DB_PASS", "postgres"),
        "HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("TEST_DB_PORT", "5432"),
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

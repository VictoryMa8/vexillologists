"""Settings used by the automated test suite."""

from .settings import *  # noqa: F403


# Django's test client sends HTTP requests unless each request opts into HTTPS.
# Production still redirects HTTP; tests disable only that transport redirect so
# requests reach the views being exercised.
SECURE_SSL_REDIRECT = False

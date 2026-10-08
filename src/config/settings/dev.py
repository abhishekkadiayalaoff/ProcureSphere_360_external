from .base import *  # noqa: F403

DEBUG = True


# Development email backend (log to console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Enable CORS for local development
CORS_ALLOW_ALL_ORIGINS = True

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models.deletion import ProtectedError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
)
from rest_framework.exceptions import (
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler returning standardized JSON error structure:
    {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Human readable error summary",
            "details": { ... field specific errors ... }
        }
    }
    """
    if isinstance(exc, ProtectedError):
        protected_list = [str(obj) for obj in exc.protected_objects]
        return Response(
            {
                "error": {
                    "code": "PROTECTED_ERROR",
                    "message": "Cannot delete record because it is referenced by other active entities.",
                    "details": {"protected_objects": protected_list},
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DjangoValidationError):
        # Domain/service-layer validation errors -> structured 400 instead of a 500.
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        exc = DRFValidationError(detail=detail)

    response = exception_handler(exc, context)

    if response is not None:
        status_code = response.status_code

        request = context.get("request") if context else None
        is_unauthenticated = isinstance(exc, NotAuthenticated) or (
            request and (not getattr(request, "user", None) or not request.user.is_authenticated)
        )

        # Derive semantic error code based on exception and status code
        if isinstance(exc, (Http404, NotFound)) or status_code == status.HTTP_404_NOT_FOUND:
            error_code = "NOT_FOUND"
        elif is_unauthenticated and status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ):
            error_code = "NOT_AUTHENTICATED"
        elif isinstance(exc, PermissionDenied) or status_code == status.HTTP_403_FORBIDDEN:
            error_code = "PERMISSION_DENIED"
        elif (
            isinstance(exc, (NotAuthenticated, AuthenticationFailed))
            or status_code == status.HTTP_401_UNAUTHORIZED
        ):
            error_code = "NOT_AUTHENTICATED"
        elif isinstance(exc, Throttled) or status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            error_code = "THROTTLED"
        elif isinstance(exc, DRFValidationError) or status_code == status.HTTP_400_BAD_REQUEST:
            error_code = "VALIDATION_ERROR"
        else:
            error_code = getattr(exc, "default_code", "API_ERROR")
            if isinstance(error_code, str):
                error_code = error_code.upper()

        def _clean_item(item):
            if isinstance(item, dict):
                return {k: _clean_item(v) for k, v in item.items()}
            if isinstance(item, (list, tuple)):
                return [_clean_item(v) for v in item]
            return str(item)

        if hasattr(exc, "detail") and isinstance(exc.detail, dict):
            details = _clean_item(exc.detail)
            message = "Validation failed for one or more fields."
        elif hasattr(exc, "detail") and isinstance(exc.detail, list):
            details = _clean_item(exc.detail)
            message = str(details[0]) if details else "Validation failed."
        elif hasattr(exc, "detail"):
            details = _clean_item(exc.detail)
            message = str(exc.detail)
        else:
            raw_data = response.data if isinstance(response.data, (dict, list)) else {}
            details = _clean_item(raw_data)
            message = str(exc)

        if "ErrorDetail(" in message:
            import re
            m = re.search(r"""ErrorDetail\(string=['"](.*?)['"]""", message)
            if m:
                message = m.group(1)

        custom_response_data = {
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
            }
        }
        return Response(custom_response_data, status=status_code)

    import logging
    logger = logging.getLogger(__name__)
    logger.exception("Unhandled server error: %s", exc)

    return Response(
        {
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "details": str(exc),
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

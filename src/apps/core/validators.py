import os

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "xlsx", "csv"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def validate_file_upload(file):
    """
    Validates uploaded file size and extension.
    """
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(_("File size exceeds maximum allowed limit of 10MB."))

    ext = os.path.splitext(file.name)[1][1:].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            _(
                f"File extension '.{ext}' is not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        )
    return file

from django.core.exceptions import ValidationError

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}
ALLOWED_RESUME_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_resume(file):
    """
    Validate uploaded resume files.
    Checks: file extension, MIME type, and file size.
    """
    import os

    # Check extension
    _, ext = os.path.splitext(file.name)
    if ext.lower() not in ALLOWED_RESUME_EXTENSIONS:
        raise ValidationError(
            f"Resume must be a PDF, DOC, or DOCX file. Got: {ext}"
        )

    # Check file size
    if file.size > MAX_RESUME_SIZE_BYTES:
        raise ValidationError(
            f"Resume file size must not exceed 5MB. Got: {file.size / (1024 * 1024):.1f}MB"
        )

    # Check MIME type (if available)
    content_type = getattr(file, "content_type", None)
    if content_type and content_type not in ALLOWED_RESUME_MIME_TYPES:
        raise ValidationError(
            f"Resume must be a PDF, DOC, or DOCX file. Got content type: {content_type}"
        )

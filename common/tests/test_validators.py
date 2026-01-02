"""
Tests for validate_resume file validator.
"""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from common.validators import validate_resume


class TestValidateResume:
    @pytest.mark.parametrize(
        "filename,content_type",
        [
            ("resume.pdf", "application/pdf"),
            ("resume.doc", "application/msword"),
            (
                "resume.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ],
    )
    def test_valid_file_passes(self, filename, content_type):
        """PDF, DOC, and DOCX files under 5MB are accepted."""
        file = SimpleUploadedFile(
            name=filename,
            content=b"%PDF-1.4 fake content",
            content_type=content_type,
        )
        # Should not raise
        validate_resume(file)

    @pytest.mark.parametrize(
        "filename",
        [
            "malware.exe",
            "script.py",
            "photo.jpg",
            "notes.txt",
            "archive.zip",
        ],
    )
    def test_wrong_extension_raises(self, filename):
        """Non-resume file extensions are rejected."""
        file = SimpleUploadedFile(
            name=filename,
            content=b"fake content",
            content_type="application/octet-stream",
        )
        with pytest.raises(ValidationError, match="PDF, DOC, or DOCX"):
            validate_resume(file)

    def test_file_too_large_raises(self):
        """Files exceeding 5MB are rejected."""
        content = b"x" * (5 * 1024 * 1024 + 1)  # 5MB + 1 byte
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=content,
            content_type="application/pdf",
        )
        with pytest.raises(ValidationError, match="must not exceed 5MB"):
            validate_resume(file)

    def test_file_exactly_at_limit_passes(self):
        """Files exactly at 5MB are accepted."""
        content = b"x" * (5 * 1024 * 1024)  # Exactly 5MB
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=content,
            content_type="application/pdf",
        )
        # Should not raise
        validate_resume(file)

    def test_wrong_mime_type_raises(self):
        """Files with valid extension but wrong MIME type are rejected."""
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=b"fake content",
            content_type="image/jpeg",
        )
        with pytest.raises(ValidationError, match="PDF, DOC, or DOCX"):
            validate_resume(file)

    def test_missing_content_type_does_not_crash(self):
        """Files without content_type attribute are handled gracefully."""
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        # Remove content_type to simulate edge case
        file.content_type = None
        # Should not raise — skips MIME check when content_type is None/falsy
        validate_resume(file)

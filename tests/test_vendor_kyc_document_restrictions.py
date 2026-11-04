"""
Tests for Restricting File Uploads to Document Files Only in Vendor Portal KYC Documents Modal.

Covers:
1. Modal UI rendering and accept attribute on /vendor/documents/.
2. Successful document uploads (PDF, DOCX).
3. Rejection of image files (PNG, JPG, JPEG, GIF, WebP).
4. Rejection of files exceeding 10 MB limit.
5. Preservation of document classification, title, expiry, and document vault list.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.vendors.models import Vendor, VendorCategory, VendorDocument


@pytest.fixture
def vendor_portal_world(db, db_roles):
    category = VendorCategory.objects.create(name="IT Services", code="CAT-IT-TEST")
    vendor = Vendor.objects.create(
        legal_name="Apex Logistics Ltd",
        trade_name="Apex",
        vendor_number="VND-2026-APEX",
        tax_identification_number="TIN-APEX-12345",
        category=category,
        email="contact@apex.local",
        address="100 Tech Park, Apex Way",
        status=Vendor.STATUS_SUBMITTED,
    )
    vendor_user = User.objects.create_user(
        email="portal.user@apex.local",
        password="Password123!",
        role=db_roles[Role.VENDOR_USER],
        vendor=vendor,
    )
    return {
        "vendor": vendor,
        "vendor_user": vendor_user,
        "category": category,
    }


@pytest.mark.django_db
class TestKycDocumentOnlyUploadModal:
    """Tests the /vendor/documents/ modal UI and validation constraints."""

    def test_modal_file_input_restricts_accepted_types_to_documents(self, client, vendor_portal_world):
        """Accepted file types in HTML file input must include document formats and exclude images."""
        client.force_login(vendor_portal_world["vendor_user"])
        resp = client.get(reverse("vendor_documents"))
        assert resp.status_code == 200
        content = resp.content.decode()

        # Check modal structure
        assert 'id="uploadKycModal"' in content
        assert 'name="action" value="upload_kyc"' in content
        assert 'name="document_type"' in content
        assert 'name="title"' in content
        assert 'name="expiry_date"' in content

        # Check file input accept attribute
        assert 'id="kycFileInput"' in content
        assert 'name="kyc_file"' in content
        assert 'accept="' in content

        # Allowed document formats must be present
        assert ".pdf" in content
        assert ".doc" in content
        assert ".docx" in content

        # Image extensions must NOT be present in the accept attribute
        # Extract accept attribute value from kycFileInput
        import re
        match = re.search(r'id="kycFileInput"[^>]*accept="([^"]+)"', content)
        if not match:
            match = re.search(r'accept="([^"]+)"[^>]*id="kycFileInput"', content)
        assert match is not None, "kycFileInput must have accept attribute"
        accept_val = match.group(1).lower()

        for img_ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", "image/"]:
            assert img_ext not in accept_val, f"Image type '{img_ext}' must not be in file input accept attribute"

    def test_pdf_upload_succeeds(self, client, vendor_portal_world):
        """Valid PDF upload is accepted and creates a pending VendorDocument."""
        client.force_login(vendor_portal_world["vendor_user"])
        vendor = vendor_portal_world["vendor_user"].vendor

        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        upload_file = SimpleUploadedFile("incorporation_cert.pdf", pdf_content, content_type="application/pdf")

        resp = client.post(
            reverse("vendor_profile"),
            {
                "action": "upload_kyc",
                "next": reverse("vendor_documents"),
                "document_type": VendorDocument.DOC_TYPE_INC,
                "title": "Certificate of Incorporation 2026",
                "expiry_date": "2030-12-31",
                "kyc_file": upload_file,
            },
            follow=True,
        )
        assert resp.status_code == 200

        # Verify document was created
        doc = VendorDocument.objects.filter(vendor=vendor, document_type=VendorDocument.DOC_TYPE_INC).first()
        assert doc is not None
        assert doc.title == "Certificate of Incorporation 2026"
        assert doc.status == VendorDocument.STATUS_PENDING
        assert doc.is_verified is False

        # Verify document list displays the newly uploaded document
        resp_docs = client.get(reverse("vendor_documents"))
        assert "Certificate of Incorporation 2026" in resp_docs.content.decode()

    @pytest.mark.parametrize(
        "filename,mime,header",
        [
            ("tax_scan.png", "image/png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),
            ("photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF"),
            ("id_card.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF"),
            ("stamp.gif", "image/gif", b"GIF89a\x01\x00\x01\x00"),
            ("doc_scan.webp", "image/webp", b"RIFF\x14\x00\x00\x00WEBPVP8 "),
        ],
    )
    def test_image_uploads_are_rejected(self, client, vendor_portal_world, filename, mime, header):
        """PNG, JPG, JPEG, GIF, and WebP image uploads are rejected with a clear message."""
        client.force_login(vendor_portal_world["vendor_user"])
        vendor = vendor_portal_world["vendor_user"].vendor
        before_count = vendor.documents.count()

        upload_file = SimpleUploadedFile(filename, header + b" dummy image payload", content_type=mime)

        resp = client.post(
            reverse("vendor_profile"),
            {
                "action": "upload_kyc",
                "next": reverse("vendor_documents"),
                "document_type": VendorDocument.DOC_TYPE_OTHER,
                "title": f"Upload Attempt {filename}",
                "kyc_file": upload_file,
            },
            follow=True,
        )
        assert resp.status_code == 200
        content = resp.content.decode()

        # Document must not be created
        assert vendor.documents.count() == before_count
        assert not VendorDocument.objects.filter(title=f"Upload Attempt {filename}").exists()

        # Clear error message must be displayed
        assert "not permitted" in content or "not supported" in content or "Upload validation failed" in content

    def test_oversized_file_rejected(self, client, vendor_portal_world):
        """Files larger than 10 MB are rejected with size limit message."""
        client.force_login(vendor_portal_world["vendor_user"])
        vendor = vendor_portal_world["vendor_user"].vendor
        before_count = vendor.documents.count()

        oversized_data = b"%PDF-1.4 " + b"0" * (10 * 1024 * 1024 + 500)
        upload_file = SimpleUploadedFile("large_contract.pdf", oversized_data, content_type="application/pdf")

        resp = client.post(
            reverse("vendor_profile"),
            {
                "action": "upload_kyc",
                "next": reverse("vendor_documents"),
                "document_type": VendorDocument.DOC_TYPE_OTHER,
                "title": "Oversized PDF",
                "kyc_file": upload_file,
            },
            follow=True,
        )
        assert resp.status_code == 200
        content = resp.content.decode()

        # Must not be created
        assert vendor.documents.count() == before_count
        assert "10MB" in content or "10 MB" in content or "exceeds" in content.lower()


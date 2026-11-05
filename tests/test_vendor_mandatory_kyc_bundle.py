"""
Tests for Mandatory PAN, TAX, and BANK KYC Document Bundle Upload in Vendor Dashboard.

Requirements:
1. Mandatory Documents: PAN (DOC_TYPE_PAN), TAX (DOC_TYPE_GST), BANK (DOC_TYPE_BANK) + optional Other.
2. Single-submission workflow with one "Upload All Documents" button.
3. Strict validation: all 3 mandatory documents required, formats (PDF, DOC, DOCX, XLSX, CSV),
   max 10MB per file, reject images (PNG, JPG, etc.), reject 0-byte files.
4. Backend integration: vendor isolation, versioning / replacement, audit logs, pending review status.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.vendors.models import Vendor, VendorDocument

pytestmark = [pytest.mark.django_db, pytest.mark.regression]

DUMMY_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
DUMMY_DOCX = b"PK\x03\x04mock docx file content for kyc validation testing"
DUMMY_XLSX = b"PK\x03\x04mock xlsx file content for kyc validation testing"
DUMMY_CSV = b"header1,header2\nval1,val2\n"


def _make_file(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.fixture
def kyc_test_env(procurement_world, db_roles):
    """
    Sets up a vendor user and an empty vendor for KYC bundle testing.
    """
    vendor = procurement_world["vendor_b"]
    # Ensure vendor starts with no documents
    vendor.documents.all().delete()

    vendor_user = User.objects.create_user(
        email="bundle_vendor@test.local",
        password="Password123!",
        role=db_roles[Role.VENDOR_USER],
        vendor=vendor,
    )

    other_vendor = procurement_world["vendor_a"]
    other_user = procurement_world["user_a"]

    return {
        "vendor": vendor,
        "vendor_user": vendor_user,
        "other_vendor": other_vendor,
        "other_user": other_user,
    }


def test_mandatory_bundle_upload_success_all_three_docs(client, kyc_test_env):
    """
    Scenario 1: Upload all 3 mandatory documents (PAN, TAX, BANK) in one submission.
    Verifies that:
    - 3 VendorDocument records are created with correct document_type
    - Status is PENDING, is_verified is False
    - Audit logs are recorded
    - Success message is displayed
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    pan_file = _make_file("pan_card.pdf", DUMMY_PDF, "application/pdf")
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    bank_file = _make_file("bank_cheque.pdf", DUMMY_PDF, "application/pdf")

    post_data = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": pan_file,
        "pan_title": "Corporate PAN Card",
        "tax_file": tax_file,
        "tax_title": "GST Registration Certificate",
        "bank_file": bank_file,
        "bank_title": "Cancelled Cheque",
    }

    resp = client.post(reverse("vendor_profile"), post_data, follow=True)
    assert resp.status_code == 200

    docs = vendor.documents.all()
    assert docs.count() == 3

    pan_doc = docs.get(document_type=VendorDocument.DOC_TYPE_PAN)
    assert pan_doc.title == "Corporate PAN Card"
    assert pan_doc.review_status == VendorDocument.REVIEW_PENDING
    assert not pan_doc.is_verified

    tax_doc = docs.get(document_type=VendorDocument.DOC_TYPE_GST)
    assert tax_doc.title == "GST Registration Certificate"
    assert tax_doc.review_status == VendorDocument.REVIEW_PENDING
    assert not tax_doc.is_verified

    bank_doc = docs.get(document_type=VendorDocument.DOC_TYPE_BANK)
    assert bank_doc.title == "Cancelled Cheque"
    assert bank_doc.review_status == VendorDocument.REVIEW_PENDING
    assert not bank_doc.is_verified

    # Audit logs verified
    audit_logs = AuditLog.objects.filter(
        actor=user,
        action=AuditLog.ACTION_CREATE,
        target_model="VendorDocument",
    )
    assert audit_logs.count() == 3

    # Check context in profile page
    assert resp.context["has_all_mandatory_docs"] is True
    assert resp.context["doc_pan"] == pan_doc
    assert resp.context["doc_tax"] == tax_doc
    assert resp.context["doc_bank"] == bank_doc


def test_mandatory_bundle_upload_with_optional_other_document(client, kyc_test_env):
    """
    Scenario 2: Upload all 3 mandatory documents PLUS an optional 4th document (OTHER / INC_CERT).
    Verifies that 4 documents are created correctly.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    pan_file = _make_file("pan_card.pdf", DUMMY_PDF, "application/pdf")
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    bank_file = _make_file("bank_cheque.pdf", DUMMY_PDF, "application/pdf")
    other_file = _make_file("incorporation.pdf", DUMMY_PDF, "application/pdf")

    post_data = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": pan_file,
        "tax_file": tax_file,
        "bank_file": bank_file,
        "other_file": other_file,
        "other_doc_type": VendorDocument.DOC_TYPE_INC,
        "other_title": "Certificate of Incorporation",
    }

    resp = client.post(reverse("vendor_profile"), post_data, follow=True)
    assert resp.status_code == 200

    docs = vendor.documents.all()
    assert docs.count() == 4

    other_doc = docs.get(document_type=VendorDocument.DOC_TYPE_INC)
    assert other_doc.title == "Certificate of Incorporation"
    assert other_doc.review_status == VendorDocument.REVIEW_PENDING
    assert not other_doc.is_verified


def test_mandatory_bundle_blocks_if_any_mandatory_doc_missing(client, kyc_test_env):
    """
    Scenarios 3 & 4:
    - Upload only PAN (missing TAX and BANK) -> blocked.
    - Upload PAN and TAX but omit BANK -> blocked.
    No documents must be saved.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    pan_file = _make_file("pan_card.pdf", DUMMY_PDF, "application/pdf")

    # Only PAN
    post_data_pan_only = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": pan_file,
    }
    resp = client.post(reverse("vendor_profile"), post_data_pan_only, follow=True)
    assert resp.status_code == 200
    assert vendor.documents.count() == 0
    messages = [m.message for m in resp.context["messages"]]
    assert any("TAX Document is mandatory" in m for m in messages)
    assert any("BANK Document is mandatory" in m for m in messages)

    # PAN and TAX without BANK
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    pan_file_2 = _make_file("pan_card.pdf", DUMMY_PDF, "application/pdf")
    post_data_pan_tax = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": pan_file_2,
        "tax_file": tax_file,
    }
    resp2 = client.post(reverse("vendor_profile"), post_data_pan_tax, follow=True)
    assert resp2.status_code == 200
    assert vendor.documents.count() == 0
    messages2 = [m.message for m in resp2.context["messages"]]
    assert any("BANK Document is mandatory" in m for m in messages2)


def test_mandatory_bundle_rejects_disallowed_image_files(client, kyc_test_env):
    """
    Scenario 7: Attempting to upload image files (PNG, JPG, etc.) must be rejected.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    # PNG file for PAN
    bad_pan = _make_file("pan_card.png", b"\x89PNG\r\n\x1a\nfake png data", "image/png")
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    bank_file = _make_file("bank_cheque.pdf", DUMMY_PDF, "application/pdf")

    post_data = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": bad_pan,
        "tax_file": tax_file,
        "bank_file": bank_file,
    }

    resp = client.post(reverse("vendor_profile"), post_data, follow=True)
    assert resp.status_code == 200
    assert vendor.documents.count() == 0
    messages = [m.message for m in resp.context["messages"]]
    assert any("Image files" in m for m in messages)


def test_mandatory_bundle_rejects_invalid_file_formats(client, kyc_test_env):
    """
    Scenario 5: Attempting to upload invalid file format (.exe, .txt, .zip) must be rejected.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    bad_pan = _make_file("script.exe", b"MZexecutable fake binary", "application/x-msdownload")
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    bank_file = _make_file("bank_cheque.pdf", DUMMY_PDF, "application/pdf")

    post_data = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": bad_pan,
        "tax_file": tax_file,
        "bank_file": bank_file,
    }

    resp = client.post(reverse("vendor_profile"), post_data, follow=True)
    assert resp.status_code == 200
    assert vendor.documents.count() == 0
    messages = [m.message for m in resp.context["messages"]]
    assert any("File extension '.exe' is not permitted" in m for m in messages)


def test_mandatory_bundle_rejects_file_exceeding_10mb(client, kyc_test_env):
    """
    Scenario 6: File exceeding 10 MB must be rejected.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    # 10 MB + 1 byte
    oversized_data = b"0" * (10 * 1024 * 1024 + 1)
    oversized_pan = _make_file("large_pan.pdf", oversized_data, "application/pdf")
    tax_file = _make_file("gst_certificate.pdf", DUMMY_PDF, "application/pdf")
    bank_file = _make_file("bank_cheque.pdf", DUMMY_PDF, "application/pdf")

    post_data = {
        "action": "upload_kyc",
        "upload_mode": "mandatory_bundle",
        "pan_file": oversized_pan,
        "tax_file": tax_file,
        "bank_file": bank_file,
    }

    resp = client.post(reverse("vendor_profile"), post_data, follow=True)
    assert resp.status_code == 200
    assert vendor.documents.count() == 0
    messages = [m.message for m in resp.context["messages"]]
    assert any("exceeds the maximum allowed limit of 10 MB" in m for m in messages)


def test_mandatory_bundle_document_replacement_and_versioning(client, kyc_test_env):
    """
    Scenario 9: Re-uploading a document replaces the previous one and increments the version number.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    client.force_login(user)

    # First upload
    client.post(
        reverse("vendor_profile"),
        {
            "action": "upload_kyc",
            "upload_mode": "mandatory_bundle",
            "pan_file": _make_file("pan_v1.pdf", DUMMY_PDF, "application/pdf"),
            "tax_file": _make_file("tax_v1.pdf", DUMMY_PDF, "application/pdf"),
            "bank_file": _make_file("bank_v1.pdf", DUMMY_PDF, "application/pdf"),
        },
    )
    first_pan = vendor.documents.get(document_type=VendorDocument.DOC_TYPE_PAN)
    assert first_pan.version == 1

    # Second upload replaces PAN
    client.post(
        reverse("vendor_profile"),
        {
            "action": "upload_kyc",
            "upload_mode": "mandatory_bundle",
            "pan_file": _make_file("pan_v2.pdf", DUMMY_PDF, "application/pdf"),
            "tax_file": _make_file("tax_v2.pdf", DUMMY_PDF, "application/pdf"),
            "bank_file": _make_file("bank_v2.pdf", DUMMY_PDF, "application/pdf"),
        },
    )

    second_pan = (
        vendor.documents.filter(document_type=VendorDocument.DOC_TYPE_PAN)
        .order_by("-version")
        .first()
    )
    assert second_pan.version == 2
    assert second_pan.replaces_document == first_pan


def test_vendor_document_isolation(client, kyc_test_env):
    """
    Scenario 8: Vendor document isolation - Vendor A cannot view/download Vendor B's document.
    """
    vendor = kyc_test_env["vendor"]
    user = kyc_test_env["vendor_user"]
    other_user = kyc_test_env["other_user"]

    # Upload document for vendor
    client.force_login(user)
    client.post(
        reverse("vendor_profile"),
        {
            "action": "upload_kyc",
            "upload_mode": "mandatory_bundle",
            "pan_file": _make_file("pan.pdf", DUMMY_PDF, "application/pdf"),
            "tax_file": _make_file("tax.pdf", DUMMY_PDF, "application/pdf"),
            "bank_file": _make_file("bank.pdf", DUMMY_PDF, "application/pdf"),
        },
    )
    pan_doc = vendor.documents.get(document_type=VendorDocument.DOC_TYPE_PAN)

    # Now login as other vendor user and try to access vendor's document download
    client.force_login(other_user)
    download_url = reverse(
        "vendor_portal_document_download",
        kwargs={"doc_type": "kyc", "doc_id": pan_doc.id},
    )
    resp = client.get(download_url)
    # Must be 403 forbidden
    assert resp.status_code == 403

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.vendors.models import Vendor, VendorCategory, VendorDocument
from apps.vendors.services import (
    approve_vendor_service,
    register_vendor_service,
    start_kyc_review_service,
    submit_vendor_kyc_service,
    verify_vendor_document_service,
)


@pytest.mark.django_db
def test_demo_1_vendor_onboarding_and_kyc_workflow(db_roles):
    """
    Day-90 Acceptance Demonstration 1:
    Onboard a vendor with KYC documents, conduct review, approve vendor, and verify append-only audit trail.
    """
    # 1. Setup users
    proc_exec = User.objects.create_user(
        email="proc_exec@hpe.com", password="Password123!", role=db_roles[Role.PROC_EXEC]
    )
    proc_mgr = User.objects.create_user(
        email="proc_mgr@hpe.com", password="Password123!", role=db_roles[Role.PROC_MGR]
    )

    # 2. Create Vendor Category
    category = VendorCategory.objects.create(
        name="IT Hardware", code="CAT-HW", description="Compute and Storage"
    )

    # 3. Register Vendor in DRAFT state
    vendor = register_vendor_service(
        legal_name="Acme Technology Solutions Inc.",
        tax_identification_number="TIN-ACME-99812",
        category=category,
        email="contact@acme.com",
        address="100 Innovation Way, San Jose, CA",
        bank_name="Global Commercial Bank",
        bank_account_number="9876543210",
        created_by_user=proc_exec,
    )

    assert vendor.status == Vendor.STATUS_DRAFT
    assert vendor.vendor_number.startswith("VND-")

    # 4. Upload KYC Document
    kyc_file = SimpleUploadedFile(
        "certificate_of_inc.pdf",
        b"%PDF-1.4 Fake Certificate of Incorporation Content",
        content_type="application/pdf",
    )
    doc = VendorDocument.objects.create(
        vendor=vendor,
        document_type=VendorDocument.DOC_TYPE_CERT,
        title="Certificate of Incorporation",
        file=kyc_file,
    )
    assert doc.id is not None
    assert doc.is_verified is False

    # 5. Submit Vendor KYC -> status SUBMITTED
    vendor = submit_vendor_kyc_service(vendor=vendor, user=proc_exec)
    assert vendor.status == Vendor.STATUS_SUBMITTED

    # 6. Start KYC Review -> status KYC_REVIEW
    vendor = start_kyc_review_service(vendor=vendor, reviewer=proc_exec)
    assert vendor.status == Vendor.STATUS_KYC_REVIEW

    # 7. Verify KYC Document
    doc = verify_vendor_document_service(document=doc, verifier=proc_exec)
    assert doc.is_verified is True
    assert doc.verified_by == proc_exec

    # 8. Approve Vendor -> status ACTIVE
    vendor = approve_vendor_service(
        vendor=vendor, manager=proc_mgr, notes="KYC verified successfully. Approved for sourcing."
    )
    assert vendor.status == Vendor.STATUS_ACTIVE
    assert vendor.status_notes == "KYC verified successfully. Approved for sourcing."

    # 9. Verify Append-Only Audit Trail
    audit_records = AuditLog.objects.filter(
        target_model="Vendor", target_object_id=str(vendor.id)
    ).order_by("timestamp")
    assert audit_records.count() >= 4

    actions = [log.action for log in audit_records]
    assert AuditLog.ACTION_CREATE in actions
    assert AuditLog.ACTION_APPROVE in actions

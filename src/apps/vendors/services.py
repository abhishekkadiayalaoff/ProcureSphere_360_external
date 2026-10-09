from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog

from .models import Vendor, VendorCategory, VendorDocument


@transaction.atomic
def register_vendor_service(
    *,
    legal_name: str,
    tax_identification_number: str,
    category: VendorCategory,
    email: str,
    address: str,
    trade_name: str = "",
    registration_number: str = "",
    phone: str = "",
    bank_name: str = "",
    bank_account_number: str = "",
    bank_routing_code: str = "",
    created_by_user: User = None,
) -> Vendor:
    """
    Registers a new vendor in DRAFT status with unique vendor number.
    """
    if Vendor.objects.filter(tax_identification_number=tax_identification_number).exists():
        raise ValidationError(f"Vendor with tax ID '{tax_identification_number}' already exists.")

    vendor_count = Vendor.objects.count() + 1
    vendor_number = f"VND-{timezone.now().strftime('%Y')}-{vendor_count:05d}"

    vendor = Vendor.objects.create(
        legal_name=legal_name,
        trade_name=trade_name,
        vendor_number=vendor_number,
        tax_identification_number=tax_identification_number,
        registration_number=registration_number,
        category=category,
        email=email,
        phone=phone,
        address=address,
        bank_name=bank_name,
        bank_account_number=bank_account_number,
        bank_routing_code=bank_routing_code,
        status=Vendor.STATUS_DRAFT,
        created_by=created_by_user,
    )

    AuditLog.objects.create(
        actor=created_by_user,
        action=AuditLog.ACTION_CREATE,
        target_model="Vendor",
        target_object_id=str(vendor.id),
        new_state={
            "status": vendor.status,
            "vendor_number": vendor.vendor_number,
            "legal_name": vendor.legal_name,
        },
    )

    return vendor


@transaction.atomic
def submit_vendor_kyc_service(*, vendor: Vendor, user: User) -> Vendor:
    """
    Transitions Vendor state from DRAFT to SUBMITTED.
    """
    if vendor.status != Vendor.STATUS_DRAFT:
        raise ValidationError(f"Cannot submit vendor in status '{vendor.status}'. Must be DRAFT.")

    if not vendor.documents.exists():
        raise ValidationError(
            "At least one KYC document must be uploaded before submitting registration."
        )

    previous_status = vendor.status
    vendor.status = Vendor.STATUS_SUBMITTED
    vendor.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.ACTION_UPDATE,
        target_model="Vendor",
        target_object_id=str(vendor.id),
        previous_state={"status": previous_status},
        new_state={"status": vendor.status},
    )
    return vendor


@transaction.atomic
def start_kyc_review_service(*, vendor: Vendor, reviewer: User) -> Vendor:
    """
    Transitions Vendor state to KYC_REVIEW.
    """
    if vendor.status != Vendor.STATUS_SUBMITTED:
        raise ValidationError(
            f"Cannot start KYC review for vendor in status '{vendor.status}'. Must be SUBMITTED."
        )

    previous_status = vendor.status
    vendor.status = Vendor.STATUS_KYC_REVIEW
    vendor.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=reviewer,
        action=AuditLog.ACTION_UPDATE,
        target_model="Vendor",
        target_object_id=str(vendor.id),
        previous_state={"status": previous_status},
        new_state={"status": vendor.status},
    )
    return vendor


@transaction.atomic
def verify_vendor_document_service(*, document: VendorDocument, verifier: User) -> VendorDocument:
    """
    Marks a KYC document as verified.
    """
    document.is_verified = True
    document.verified_by = verifier
    document.save(update_fields=["is_verified", "verified_by", "updated_at"])
    return document


@transaction.atomic
def approve_vendor_service(*, vendor: Vendor, manager: User, notes: str = "") -> Vendor:
    """
    Approves Vendor and transitions state from KYC_REVIEW to APPROVED and ACTIVE.
    """
    if vendor.status not in [Vendor.STATUS_SUBMITTED, Vendor.STATUS_KYC_REVIEW]:
        raise ValidationError(f"Cannot approve vendor in status '{vendor.status}'.")

    # Ensure documents are uploaded
    if not vendor.documents.exists():
        raise ValidationError("Cannot approve vendor with no uploaded KYC documents.")

    previous_status = vendor.status
    vendor.status = Vendor.STATUS_ACTIVE
    vendor.status_notes = notes
    vendor.save(update_fields=["status", "status_notes", "updated_at"])

    AuditLog.objects.create(
        actor=manager,
        action=AuditLog.ACTION_APPROVE,
        target_model="Vendor",
        target_object_id=str(vendor.id),
        previous_state={"status": previous_status},
        new_state={"status": vendor.status, "notes": notes},
    )
    return vendor


@transaction.atomic
def set_vendor_status_governance_service(
    *, vendor: Vendor, actor: User, new_status: str, notes: str
) -> Vendor:
    """
    Governance service to set vendor status (HOLD, SUSPENDED, ACTIVE, REJECTED).
    """
    allowed_statuses = [
        Vendor.STATUS_ON_HOLD,
        Vendor.STATUS_SUSPENDED,
        Vendor.STATUS_ACTIVE,
        Vendor.STATUS_REJECTED,
    ]
    if new_status not in allowed_statuses:
        raise ValidationError(f"Invalid status '{new_status}'. Allowed: {allowed_statuses}")

    previous_status = vendor.status
    vendor.status = new_status
    vendor.status_notes = notes
    vendor.save(update_fields=["status", "status_notes", "updated_at"])

    AuditLog.objects.create(
        actor=actor,
        action=AuditLog.ACTION_UPDATE,
        target_model="Vendor",
        target_object_id=str(vendor.id),
        previous_state={"status": previous_status},
        new_state={"status": vendor.status, "notes": notes},
    )
    return vendor

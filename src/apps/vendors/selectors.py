from .models import Vendor, VendorDocument


def get_all_active_vendors():
    return (
        Vendor.objects.select_related("category")
        .filter(status=Vendor.STATUS_ACTIVE)
        .order_by("legal_name")
    )


def get_vendor_by_id(vendor_id):
    return (
        Vendor.objects.select_related("category")
        .prefetch_related("documents", "contacts", "risk_records")
        .filter(id=vendor_id)
        .first()
    )


def get_vendors_by_status(status_code):
    return (
        Vendor.objects.select_related("category").filter(status=status_code).order_by("-created_at")
    )


def get_vendor_documents(vendor_id):
    return (
        VendorDocument.objects.select_related("verified_by")
        .filter(vendor_id=vendor_id)
        .order_by("-created_at")
    )

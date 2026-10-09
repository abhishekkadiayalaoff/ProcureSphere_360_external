from .models import POAmendment, PurchaseOrder


def get_all_purchase_orders():
    return (
        PurchaseOrder.objects.select_related("vendor", "cost_center")
        .prefetch_related("lines", "amendments")
        .order_by("-created_at")
    )


def get_purchase_order_by_id(po_id):
    return (
        PurchaseOrder.objects.select_related("vendor", "cost_center")
        .prefetch_related("lines", "amendments")
        .filter(id=po_id)
        .first()
    )


def get_po_version_history(po_id):
    return (
        POAmendment.objects.select_related("po", "requested_by")
        .filter(po_id=po_id)
        .order_by("amendment_number")
    )

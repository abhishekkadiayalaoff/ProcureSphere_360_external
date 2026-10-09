from .models import GoodsReceipt


def get_all_goods_receipts():
    return (
        GoodsReceipt.objects.select_related("po", "received_by")
        .prefetch_related("lines")
        .order_by("-received_date")
    )


def get_goods_receipt_by_id(grn_id):
    return (
        GoodsReceipt.objects.select_related("po", "received_by")
        .prefetch_related("lines__inspection", "lines__rejections")
        .filter(id=grn_id)
        .first()
    )


def get_receipts_for_po(po_id):
    return (
        GoodsReceipt.objects.select_related("received_by")
        .prefetch_related("lines")
        .filter(po_id=po_id)
        .order_by("-received_date")
    )

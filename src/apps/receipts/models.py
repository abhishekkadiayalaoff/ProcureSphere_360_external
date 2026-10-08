from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class GoodsReceipt(TimeStampedModel):
    grn_number = models.CharField(max_length=50, unique=True)
    po = models.ForeignKey(
        "orders.PurchaseOrder", on_delete=models.PROTECT, related_name="receipts"
    )
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="received_grns"
    )
    received_date = models.DateTimeField()
    delivery_note_number = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.grn_number} for {self.po.po_number}"


class ReceiptLine(TimeStampedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    po_line = models.ForeignKey(
        "orders.POLine", on_delete=models.PROTECT, related_name="receipt_lines"
    )
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_accepted = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_rejected = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    notes = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        self.quantity_rejected = self.quantity_received - self.quantity_accepted
        super().save(*args, **kwargs)

    def __str__(self):
        return f"GRN Line: Recv {self.quantity_received}, Accept {self.quantity_accepted}, Reject {self.quantity_rejected}"


class InspectionRecord(TimeStampedModel):
    receipt_line = models.OneToOneField(
        ReceiptLine, on_delete=models.CASCADE, related_name="inspection"
    )
    inspected_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="inspections"
    )
    passed = models.BooleanField(default=True)
    inspection_notes = models.TextField()

    def __str__(self):
        return f"Inspection {'PASSED' if self.passed else 'FAILED'} by {self.inspected_by.email}"


class RejectionRecord(TimeStampedModel):
    receipt_line = models.ForeignKey(
        ReceiptLine, on_delete=models.CASCADE, related_name="rejections"
    )
    rejected_quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rejection_reason = models.TextField()
    returned_to_vendor = models.BooleanField(default=False)

    def __str__(self):
        return f"Rejection: {self.rejected_quantity} units - {self.rejection_reason[:50]}"

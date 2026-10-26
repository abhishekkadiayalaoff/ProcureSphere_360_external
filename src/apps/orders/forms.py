from decimal import Decimal

from django import forms


class POAmendForm(forms.Form):
    """Change-order form: mandatory reason + per-line quantity/unit-price edits.

    The view rebuilds ``updated_line_items`` for
    ``amend_purchase_order_service`` from these fields, preserving
    item descriptions server-side (never trusted from the client).
    """

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        help_text="Amendment justification (stored immutably in POAmendment + AuditLog).",
    )

    def __init__(self, *args, po=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.po = po
        if po is not None:
            for line in po.lines.all():
                self.fields[f"quantity_{line.id}"] = forms.DecimalField(
                    min_value=Decimal("0.01"),
                    max_digits=12,
                    decimal_places=2,
                    initial=line.quantity,
                    label=f"Qty — {line.item_description}",
                    widget=forms.NumberInput(
                        attrs={"class": "form-control form-control-sm", "step": "0.01"}
                    ),
                )
                self.fields[f"unit_price_{line.id}"] = forms.DecimalField(
                    min_value=Decimal("0.01"),
                    max_digits=12,
                    decimal_places=2,
                    initial=line.unit_price,
                    label=f"Unit price — {line.item_description}",
                    widget=forms.NumberInput(
                        attrs={"class": "form-control form-control-sm", "step": "0.01"}
                    ),
                )

    def clean_reason(self):
        reason = (self.cleaned_data.get("reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Amendment justification reason is required.")
        return reason

    def build_updated_line_items(self):
        """Rebuild line payloads using server-side descriptions + UoM."""
        items = []
        for line in self.po.lines.all():
            items.append(
                {
                    "item_description": line.item_description,
                    "quantity": self.cleaned_data[f"quantity_{line.id}"],
                    "unit_price": self.cleaned_data[f"unit_price_{line.id}"],
                    "unit_of_measure": line.unit_of_measure,
                }
            )
        return items

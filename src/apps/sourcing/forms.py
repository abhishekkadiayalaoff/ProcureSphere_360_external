from decimal import Decimal

from django import forms

from apps.requisitions.models import PurchaseRequisition

from .models import SourcingEvent

DATETIME_INPUT = forms.DateTimeInput(
    attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
)


class SourcingEventForm(forms.Form):
    title = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))
    event_type = forms.ChoiceField(
        choices=SourcingEvent.EVENT_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    requisition = forms.ModelChoiceField(
        queryset=PurchaseRequisition.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Approved requisition this event sources (optional).",
    )
    bid_start_date = forms.DateTimeField(
        widget=DATETIME_INPUT, input_formats=["%Y-%m-%dT%H:%M"], label="Bid start"
    )
    bid_end_date = forms.DateTimeField(
        widget=DATETIME_INPUT, input_formats=["%Y-%m-%dT%H:%M"], label="Bid deadline"
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        label="Scope / requirements",
    )
    technical_requirements = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"})
    )
    commercial_requirements = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"})
    )
    required_documents = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        label="Required supporting documents",
    )
    technical_weight = forms.DecimalField(
        min_value=0,
        max_value=100,
        initial=Decimal("50"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    commercial_weight = forms.DecimalField(
        min_value=0,
        max_value=100,
        initial=Decimal("50"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requisition"].queryset = PurchaseRequisition.objects.filter(
            status="APPROVED"
        ).order_by("-created_at")

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("bid_start_date"), cleaned.get("bid_end_date")
        if start and end and start >= end:
            self.add_error("bid_end_date", "Bid deadline must be after the bid start.")
        tw, cw = cleaned.get("technical_weight"), cleaned.get("commercial_weight")
        if tw is not None and cw is not None and tw + cw != Decimal("100"):
            self.add_error("commercial_weight", "Technical and commercial weights must total 100.")
        return cleaned

    @classmethod
    def initial_from_event(cls, event):
        return {
            "title": event.title,
            "event_type": event.event_type,
            "requisition": event.requisition_id,
            "bid_start_date": event.bid_start_date,
            "bid_end_date": event.bid_end_date,
            "description": event.description,
            "technical_requirements": event.technical_requirements,
            "commercial_requirements": event.commercial_requirements,
            "required_documents": event.required_documents,
            "technical_weight": event.technical_weight,
            "commercial_weight": event.commercial_weight,
        }

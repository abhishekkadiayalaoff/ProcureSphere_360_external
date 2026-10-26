from django import forms

from apps.orders.models import PurchaseOrder
from apps.sourcing.models import SourcingEvent
from apps.vendors.models import Vendor

from .models import Contract, ContractDocument, ContractMilestone, ContractObligation


class ContractCreateForm(forms.ModelForm):
    vendor = forms.ModelChoiceField(
        queryset=Vendor.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=True,
    )
    sourcing_event = forms.ModelChoiceField(
        queryset=SourcingEvent.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    po = forms.ModelChoiceField(
        queryset=PurchaseOrder.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )

    class Meta:
        model = Contract
        fields = [
            "title",
            "vendor",
            "sourcing_event",
            "po",
            "contract_value",
            "start_date",
            "end_date",
            "renewal_notice_days",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Enterprise IT Infrastructure Maintenance SLA",
                }
            ),
            "contract_value": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
            ),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "renewal_notice_days": forms.NumberInput(
                attrs={"class": "form-control", "value": "30"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("Contract end date cannot be earlier than start date.")
        return cleaned_data


class ContractAmendmentForm(forms.Form):
    amendment_summary = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "State scope change, price adjustment, or term extension details...",
            }
        ),
        required=True,
    )
    contract_value = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        required=True,
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}), required=True
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}), required=True
    )


class ContractMilestoneForm(forms.ModelForm):
    class Meta:
        model = ContractMilestone
        fields = ["title", "due_date", "amount"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Phase 1 Implementation Acceptance",
                }
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


class ContractObligationForm(forms.ModelForm):
    class Meta:
        model = ContractObligation
        fields = ["title", "responsible_party", "due_date"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Monthly SLA Uptime Report Submission",
                }
            ),
            "responsible_party": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "VENDOR / HPE LEGAL"}
            ),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class ContractDocumentForm(forms.ModelForm):
    class Meta:
        model = ContractDocument
        fields = ["title", "file"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Executed Master Service Agreement PDF",
                }
            ),
            "file": forms.FileInput(attrs={"class": "form-control"}),
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            ext = file.name.split(".")[-1].lower()
            allowed_extensions = [
                "pdf",
                "docx",
                "doc",
                "xlsx",
                "xls",
                "png",
                "jpg",
                "jpeg",
                "txt",
            ]
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    f"Unsupported file format '.{ext}'. Allowed formats: PDF, DOCX, XLSX, PNG, JPG, TXT."
                )
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("File size exceeds 10MB upload limit.")
        return file


class ContractRenewalForm(forms.Form):
    new_end_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}), required=True
    )
    new_value = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        required=False,
    )
    notes = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Renewal terms & approval notes...",
            }
        ),
        required=False,
    )

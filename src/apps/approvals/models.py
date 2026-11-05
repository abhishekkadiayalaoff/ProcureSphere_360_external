from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel


class ApprovalPolicy(TimeStampedModel):
    MODULE_PR = "PR"
    MODULE_PO = "PO"
    MODULE_SOURCING = "SOURCING"
    MODULE_INVOICE = "INVOICE"
    MODULE_VENDOR = "VENDOR"
    MODULE_PO_AMENDMENT = "PO_AMENDMENT"
    MODULE_CONTRACT = "CONTRACT"
    MODULE_BUDGET_EXCEPTION = "BUDGET_EXCEPTION"
    MODULE_VENDOR_PAYMENT = "VENDOR_PAYMENT"
    MODULE_EXPENSE_CLAIM = "EXPENSE_CLAIM"

    MODULE_CHOICES = [
        (MODULE_PR, "Purchase Requisition"),
        (MODULE_PO, "Purchase Order"),
        (MODULE_SOURCING, "Sourcing Award"),
        (MODULE_INVOICE, "Invoice Match Exception"),
        (MODULE_VENDOR, "Vendor KYC Approval"),
        (MODULE_PO_AMENDMENT, "Purchase Order Amendment"),
        (MODULE_CONTRACT, "Contract Approval"),
        (MODULE_BUDGET_EXCEPTION, "Budget Exception"),
        (MODULE_VENDOR_PAYMENT, "Vendor Payment"),
        (MODULE_EXPENSE_CLAIM, "Expense Claim"),
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_DRAFT = "DRAFT"
    STATUS_ARCHIVED = "ARCHIVED"

    EXCEPTION_BEHAVIOR_ADDITIONAL = "ADDITIONAL_APPROVER"
    EXCEPTION_BEHAVIOR_ALTERNATE = "ALTERNATE_PATH"
    EXCEPTION_BEHAVIOR_ESCALATE = "ESCALATE_ADMIN"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_DRAFT, "Draft"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    CURRENCY_CHOICES = [
        ("INR", "₹ INR"),
        ("USD", "$ USD"),
        ("EUR", "€ EUR"),
        ("GBP", "£ GBP"),
    ]

    name = models.CharField(max_length=200)
    organization = models.ForeignKey(
        "organization.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
        db_index=True,
    )
    module = models.CharField(max_length=50, choices=MODULE_CHOICES, db_index=True)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=10, default="INR", choices=CURRENCY_CHOICES)

    department = models.ForeignKey(
        "organization.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
    )
    cost_center = models.ForeignKey(
        "organization.CostCenter",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
    )
    all_departments = models.BooleanField(default=False)
    all_cost_centers = models.BooleanField(default=False)
    departments = models.ManyToManyField(
        "organization.Department",
        blank=True,
        related_name="multi_dept_policies",
    )
    cost_centers = models.ManyToManyField(
        "organization.CostCenter",
        blank=True,
        related_name="multi_cc_policies",
    )

    min_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    max_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )

    status = models.CharField(
        max_length=20, default=STATUS_ACTIVE, choices=STATUS_CHOICES, db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    version = models.PositiveIntegerField(default=1)

    # Exception Routing Configuration
    has_exception_routing = models.BooleanField(default=False)
    exception_amount_threshold = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    exception_department = models.ForeignKey(
        "organization.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    exception_cost_center = models.ForeignKey(
        "organization.CostCenter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    exception_trigger_on_missing_cost_center = models.BooleanField(default=False)
    exception_trigger_on_budget_exceeded = models.BooleanField(default=False)
    exception_approver_role = models.ForeignKey(
        "accounts.Role",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    exception_specific_approver = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    exception_escalation_time_hours = models.PositiveIntegerField(
        null=True, blank=True, default=24
    )
    exception_routing_behavior = models.CharField(
        max_length=50,
        default="ADDITIONAL_APPROVER",
        choices=[
            ("ADDITIONAL_APPROVER", "Additional Approver (Appended to Chain)"),
            ("ALTERNATE_PATH", "Alternate Approval Path (Replaces Chain)"),
            ("ESCALATE_ADMIN", "Escalate to Admin Review"),
        ],
    )
    exception_reason = models.CharField(max_length=255, blank=True)
    exception_description = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.min_amount is not None and self.min_amount < Decimal("0.00"):
            raise ValidationError({"min_amount": "Minimum amount cannot be negative."})
        if self.max_amount is not None and self.min_amount is not None:
            if self.min_amount > self.max_amount:
                raise ValidationError(
                    {"min_amount": "Minimum amount cannot be greater than maximum amount."}
                )
        if self.department and self.cost_center:
            if self.cost_center.department_id != self.department.id:
                raise ValidationError(
                    {
                        "cost_center": f"Cost center '{self.cost_center.code}' does not belong to department '{self.department.name}'."
                    }
                )
        if self.organization and self.department:
            if self.department.organization_id != self.organization.id:
                raise ValidationError(
                    {"department": "Department does not belong to the selected organization."}
                )

        # Conflict & Overlap Detection for Active Policies
        if self.is_active and self.status == self.STATUS_ACTIVE:
            qs = ApprovalPolicy.objects.filter(
                is_active=True,
                status=self.STATUS_ACTIVE,
                module=self.module,
                organization=self.organization,
                department=self.department,
                cost_center=self.cost_center,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            for existing in qs:
                e_min = existing.min_amount
                e_max = existing.max_amount
                c_min = self.min_amount
                c_max = self.max_amount

                overlap = (e_max is None or c_min <= e_max) and (c_max is None or e_min <= c_max)
                if overlap:
                    e_range = f"{existing.min_amount} - {existing.max_amount or 'Unlimited'}"
                    raise ValidationError(
                        f"Amount range overlaps with existing active policy '{existing.name}' ({e_range}). "
                        "Conflicting overlapping policies with identical scope are not permitted."
                    )

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_ACTIVE:
            self.is_active = True
        elif self.status in [self.STATUS_DRAFT, self.STATUS_ARCHIVED]:
            self.is_active = False

        if not self.organization_id:
            if self.department_id and self.department:
                self.organization = self.department.organization
            elif self.cost_center_id and self.cost_center and self.cost_center.department:
                self.organization = self.cost_center.department.organization

        super().save(*args, **kwargs)

    def __str__(self):
        curr_symbol = "₹" if self.currency == "INR" else ("$" if self.currency == "USD" else self.currency)
        return f"{self.name} [{self.module}] (Min: {curr_symbol}{self.min_amount})"


class ApprovalStep(TimeStampedModel):
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.CASCADE, related_name="steps"
    )
    step_number = models.PositiveIntegerField()
    approver_role = models.ForeignKey(
        "accounts.Role", on_delete=models.PROTECT, related_name="approval_steps"
    )
    specific_approver = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_approval_steps",
    )
    description = models.CharField(max_length=255, blank=True)

    is_mandatory = models.BooleanField(default=True)
    approval_limit = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    step_type = models.CharField(
        max_length=20,
        default="SEQUENTIAL",
        choices=[("SEQUENTIAL", "Sequential"), ("PARALLEL", "Parallel")],
    )
    rejection_behavior = models.CharField(
        max_length=30,
        default="STOP_WORKFLOW",
        choices=[
            ("STOP_WORKFLOW", "Stop and Reject Workflow"),
            ("RETURN_TO_PREVIOUS", "Return to Previous Approver"),
            ("RETURN_TO_REQUESTER", "Return to Requester for Revision"),
        ],
    )
    escalation_hours = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["step_number"]
        unique_together = ("policy", "step_number")

    def __str__(self):
        return (
            f"Step {self.step_number}: {self.approver_role.name} for {self.policy.name}"
        )


class ApprovalAction(TimeStampedModel):
    ACTION_SUBMIT = "SUBMITTED"
    ACTION_APPROVE = "APPROVED"
    ACTION_REJECT = "REJECTED"
    ACTION_DELEGATE = "DELEGATED"

    ACTION_CHOICES = [
        (ACTION_SUBMIT, "Submitted"),
        (ACTION_APPROVE, "Approved"),
        (ACTION_REJECT, "Rejected"),
        (ACTION_DELEGATE, "Delegated"),
    ]

    policy_step = models.ForeignKey(
        ApprovalStep, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_object_id = models.UUIDField(db_index=True)
    target_model_name = models.CharField(max_length=100)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="approval_actions"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    previous_state = models.CharField(max_length=100)
    new_state = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.action} by {self.actor.email} on {self.target_model_name} ({self.target_object_id})"


class ApprovalDelegate(TimeStampedModel):
    approver = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="delegator_records"
    )
    delegate = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="delegated_records"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    reason = models.TextField(blank=True)

    def __str__(self):
        return f"Delegate {self.delegate.email} for {self.approver.email} ({self.start_date} to {self.end_date})"

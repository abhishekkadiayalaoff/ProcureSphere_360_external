from django.contrib import admin

from .models import Budget, BudgetReservation, SpendLedger


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = (
        "cost_center",
        "fiscal_period",
        "allocated_amount",
        "reserved_amount",
        "committed_amount",
        "actual_amount",
        "available_amount",
        "allow_overspend",
    )
    list_filter = ("cost_center", "fiscal_period", "allow_overspend")
    search_fields = ("cost_center__code", "cost_center__name")


@admin.register(BudgetReservation)
class BudgetReservationAdmin(admin.ModelAdmin):
    list_display = ("budget", "requisition", "amount", "status", "created_at")
    list_filter = ("status", "budget__cost_center")
    search_fields = ("requisition__pr_number",)


@admin.register(SpendLedger)
class SpendLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "budget",
        "entry_type",
        "amount",
        "reference_number",
        "description",
        "created_at",
    )
    list_filter = ("entry_type", "budget__cost_center")
    search_fields = ("reference_number", "description")

from .models import Budget, SpendLedger


def get_budget_by_cost_center(cost_center_id, fiscal_period_id=None):
    queryset = Budget.objects.select_related("cost_center", "fiscal_period").filter(
        cost_center_id=cost_center_id
    )
    if fiscal_period_id:
        return queryset.filter(fiscal_period_id=fiscal_period_id).first()
    return queryset.first()


def get_spend_ledger_entries(cost_center_id):
    return (
        SpendLedger.objects.select_related("budget__cost_center")
        .filter(budget__cost_center_id=cost_center_id)
        .order_by("-created_at")
    )

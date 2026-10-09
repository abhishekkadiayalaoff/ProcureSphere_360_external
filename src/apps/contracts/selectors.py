from .models import Contract, ContractAlert


def get_all_contracts():
    return (
        Contract.objects.select_related("vendor", "contract_owner")
        .prefetch_related("milestones", "alerts")
        .order_by("-created_at")
    )


def get_contract_by_id(contract_id):
    return (
        Contract.objects.select_related("vendor", "contract_owner")
        .prefetch_related("milestones", "alerts", "versions")
        .filter(id=contract_id)
        .first()
    )


def get_active_contract_alerts():
    return (
        ContractAlert.objects.select_related("contract")
        .filter(is_processed=False)
        .order_by("-triggered_at")
    )

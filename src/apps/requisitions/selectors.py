from .models import PurchaseRequisition


def get_all_requisitions():
    return (
        PurchaseRequisition.objects.select_related("requester", "department", "cost_center")
        .prefetch_related("lines", "attachments")
        .order_by("-created_at")
    )


def get_requisition_by_id(pr_id):
    return (
        PurchaseRequisition.objects.select_related("requester", "department", "cost_center")
        .prefetch_related("lines", "attachments")
        .filter(id=pr_id)
        .first()
    )


def get_requisitions_by_department(department_id):
    return (
        PurchaseRequisition.objects.select_related("requester", "cost_center")
        .filter(department_id=department_id)
        .order_by("-created_at")
    )

from django.db.models import Q

from apps.accounts.models import Role


def scope_invoices_queryset(qs, user):
    """
    Enforces role-based and organizational tenant isolation on Supplier Invoices:
    - Superuser: unrestricted access across all invoices.
    - Vendor user: strictly isolated to their own vendor organization.
    - Internal roles (Auditor, Procurement Manager, Finance AP, etc.):
      Strictly scoped to their effective_organization. Cannot view other orgs.
    """
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs

    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    if getattr(user, "is_vendor", False) or role_code == Role.VENDOR_USER:
        vendor_id = getattr(user, "vendor_id", None)
        return qs.filter(vendor_id=vendor_id) if vendor_id else qs.none()

    scoped_org = getattr(user, "effective_organization", None)
    if scoped_org:
        return qs.filter(
            Q(po__cost_center__department__organization=scoped_org)
            | Q(po__requisition__department__organization=scoped_org)
            | Q(vendor__organization=scoped_org)
            | Q(po__cost_center__isnull=True, vendor__organization__isnull=True)
        )

    return qs

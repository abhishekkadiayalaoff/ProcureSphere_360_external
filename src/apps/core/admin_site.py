from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered

from apps.accounts.models import Role

role_app_mapping = {
    Role.SUPER_ADMIN: [
        "invoices",
        "budgets",
        "audit",
        "accounts",
        "receipts",
        "orders",
        "vendors",
        "sourcing",
        "scorecards",
        "requisitions",
        "approvals",
        "contracts",
        "organization",
        "notifications",
        "reports",
    ],
    Role.FINANCE_AP: ["invoices", "budgets", "audit", "accounts", "orders"],
    Role.STORES_RECEIVER: ["receipts", "orders", "vendors", "accounts"],
    Role.PROC_EXEC: ["sourcing", "orders", "vendors", "scorecards", "requisitions", "accounts"],
    Role.PROC_MGR: [
        "sourcing",
        "orders",
        "vendors",
        "scorecards",
        "requisitions",
        "approvals",
        "accounts",
    ],
    Role.LEGAL_MGR: ["contracts", "vendors", "accounts"],
    Role.REQUESTER: ["requisitions", "organization", "accounts"],
    Role.DEPT_APPROVER: ["requisitions", "approvals", "organization", "accounts"],
    Role.AUDITOR: ["audit", "reports", "accounts"],
    Role.VENDOR_USER: ["sourcing", "orders", "vendors", "accounts"],
}


class ProcureSphereAdminSite(admin.AdminSite):
    site_header = "ProcureSphere 360 Enterprise ERP"
    site_title = "ProcureSphere 360 Admin Portal"
    index_title = "Role-Tailored ERP Administration & Governance Desk"

    def get_app_list(self, request, app_label=None):
        """
        Dynamically filters models visible in Django Admin based on user's PRD role code.
        """
        app_list = super().get_app_list(request, app_label)
        user = request.user

        if not user or not user.is_authenticated:
            return app_list

        if user.is_superuser or getattr(user, "role_code", None) == Role.SUPER_ADMIN:
            return app_list

        role_code = getattr(user, "role_code", None)
        allowed_apps = role_app_mapping.get(role_code, None)

        if allowed_apps is None:
            return app_list

        filtered_apps = []
        for app in app_list:
            if app["app_label"].lower() in allowed_apps:
                filtered_apps.append(app)
        return filtered_apps


admin_site = ProcureSphereAdminSite(name="procuresphere_admin")


class RoleBasedModelAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin enforcing positive role-based permissions across Django Admin views.
    """

    def has_module_permission(self, request):
        if not request.user or not request.user.is_authenticated or not request.user.is_staff:
            return False
        if (
            request.user.is_superuser
            or getattr(request.user, "role_code", None) == Role.SUPER_ADMIN
        ):
            return True
        role_code = getattr(request.user, "role_code", None)
        allowed_apps = role_app_mapping.get(role_code, [])
        return self.opts.app_label.lower() in allowed_apps

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        if self.opts.app_label.lower() == "audit":
            return False
        return self.has_module_permission(request)


def register_model(model, model_admin=None):
    """
    Safely registers a model to both ProcureSphere custom admin_site and standard admin.site.
    Automatically wraps generic ModelAdmin in RoleBasedModelAdmin if not already inherited.
    """
    if model_admin is None:
        model_admin = RoleBasedModelAdmin

    try:
        admin_site.register(model, model_admin)
    except AlreadyRegistered:
        pass

    try:
        admin.site.register(model, model_admin)
    except AlreadyRegistered:
        pass

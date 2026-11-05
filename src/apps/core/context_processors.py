from django.conf import settings as django_settings

from apps.accounts.models import Role


def seo_context(request):
    """Provides default SEO metadata to all templates."""
    site_url = getattr(django_settings, "SITE_URL", "https://procuresphere.com").rstrip("/")
    return {
        "site_name": "ProcureSphere 360",
        "site_url": site_url,
        "default_og_image": f"{site_url}/static/icons/og-image.png",
        "site_twitter_handle": "@procuresphere",
    }


def layout_context(request):
    """
    Provides dynamic base_layout template name based on authenticated user role.
    Ensures role-specific pages and shared models render inside the correct role workspace.
    """
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if hasattr(user, "role") and user.role else None
        )
        if user.is_superuser or role_code in [Role.SUPER_ADMIN, "SUPER_ADMIN", "ADMIN"]:
            return {"base_layout": "layouts/superadmin_base.html"}
        elif role_code in [Role.PROC_MGR, "PROC_MGR"]:
            return {"base_layout": "manager/base_manager.html"}
        elif role_code in [Role.PROC_EXEC, "PROC_EXEC"]:
            # Procurement Executive workspace intentionally renders with base.html (embeds proc_exec_sidebar.html)
            return {"base_layout": "base.html"}
        elif role_code in [Role.LEGAL_MGR, "LEGAL_MGR"]:
            return {"base_layout": "layouts/legal_base.html"}
        elif role_code in [Role.STORES_RECEIVER, "STORES_RECEIVER"]:
            return {"base_layout": "layouts/stores_base.html"}
        elif role_code in [Role.AUDITOR, "AUDITOR"]:
            return {"base_layout": "audit/base_auditor.html"}
        elif role_code in [Role.FINANCE_AP, "FINANCE_AP"]:
            return {"base_layout": "layouts/finance_base.html"}
        elif role_code in [Role.DEPT_APPROVER, "DEPT_APPROVER"]:
            return {"base_layout": "layouts/approver_base.html"}
        elif role_code in [Role.VENDOR_USER, "VENDOR_USER"]:
            return {"base_layout": "layouts/vendor_base.html"}
        elif role_code in [Role.REQUESTER, "REQUESTER"]:
            return {"base_layout": "layouts/requester_base.html"}
    return {}

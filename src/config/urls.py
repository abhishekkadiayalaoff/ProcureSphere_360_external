from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic.base import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.api_views import SessionLoginView, SessionLogoutView
from apps.accounts.views import (
    change_password_view,
    password_change_view,
    portal_login_view,
    portal_logout_view,
)
from apps.core.seo_views import robots_txt, sitemap_xml
from apps.core.views import (
    custom_404_view,
    home_view,
    protected_media_view,
    protected_vendor_document_view,
)

from .healthchecks import health, readyz

urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("favicon.ico", RedirectView.as_view(url="/static/icons/favicon.ico", permanent=False), name="favicon"),
    path("health", health, name="health"),
    path("readyz", readyz, name="readyz"),
    re_path(r"^.*prompts\.json$", lambda request: JsonResponse({})),
    path("admin/dashboard/", home_view, name="admin_dashboard"),
    path("admin/logout/", portal_logout_view, name="admin_logout_override"),
    path("admin/", admin.site.urls),
    path("login/", portal_login_view, name="login"),
    path("login", portal_login_view),
    path("logout", portal_logout_view),
    path("logout/", portal_logout_view, name="logout"),
    path("password-change/", password_change_view, name="password_change"),
    path("accounts/change-password/", change_password_view, name="change_password"),

    # Superadmin, Manager & Vendor Portals
    path("superadmin/", include("apps.core.superadmin_urls")),
    path("manager/", include("apps.core.manager_urls")),
    path("manager/api/", include("apps.core.manager_api_urls")),
    path("vendor/", include("apps.vendors.vendor_dashboard_urls")),

    # Public landing website - included BEFORE apps.core.urls so that
    # anonymous traffic to "/" resolves to landing_home. Authenticated
    # users are forwarded inside landing_home via direct Python call.
    path("", include("apps.core.landing_urls")),

    # Core & Auth & Page Views
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.requisitions.urls")),
    path("", include("apps.approvals.urls")),
    path("", include("apps.vendors.urls")),
    path("", include("apps.sourcing.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.receipts.urls")),
    path("invoices/", include("apps.invoices.urls")),
    path("", include("apps.contracts.urls")),
    path("", include("apps.scorecards.urls")),
    path("", include("apps.notifications.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", include("apps.audit.urls")),
    path("budgets/", include("apps.budgets.urls")),

    # REST API v1
    path("api/v1/auth/token/", SessionLoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", SessionLoginView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout/", SessionLogoutView.as_view(), name="session_logout"),
    path("api/v1/auth/", include("apps.accounts.api_urls")),
    path("api/v1/accounts/", include("apps.accounts.api_urls")),
    path("api/v1/organization/", include("apps.organization.api_urls")),
    path("api/v1/approvals/", include("apps.approvals.api_urls")),
    path("api/v1/vendors/", include("apps.vendors.api_urls")),
    path("api/v1/requisitions/", include("apps.requisitions.api_urls")),
    path("api/v1/sourcing/", include("apps.sourcing.api_urls")),
    path("api/v1/sourcing-events/", include("apps.sourcing.api_urls")),
    path("api/v1/orders/", include("apps.orders.api_urls")),
    path("api/v1/purchase-orders/", include("apps.orders.api_urls")),
    path("api/v1/receipts/", include("apps.receipts.api_urls")),
    path("api/v1/invoices/", include("apps.invoices.api_urls")),
    path("api/v1/contracts/", include("apps.contracts.api_urls")),
    path("api/v1/scorecards/", include("apps.scorecards.api_urls")),
    path("api/v1/budgets/", include("apps.budgets.api_urls")),
    path("api/v1/notifications/", include("apps.notifications.api_urls")),
    path("api/v1/reports/", include("apps.reports.api_urls")),
    path("api/v1/audit/", include("apps.audit.api_urls")),
    path("api/v1/manager/", include("apps.core.manager_api_urls")),

    # OpenAPI Schema & Documentation
    path("api/schema", SpectacularAPIView.as_view()),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # Protected Media Serving (Audit-controlled access)
    re_path(
        r"^media/vendor_docs/(?P<file_path>.*)$",
        protected_vendor_document_view,
        name="protected_vendor_document",
    ),
    path("media/vendor_documents/<path:file_path>", protected_vendor_document_view, name="protected_vendor_document_alt"),
    re_path(r"^media/(?P<file_path>.*)$", protected_media_view, name="protected_media"),
]

# Custom HTTP Error Handlers
handler404 = custom_404_view
handler500 = "apps.core.views.custom_500_view"

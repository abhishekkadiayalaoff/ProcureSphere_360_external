
from django.urls import path

from . import superadmin_views

app_name = "superadmin"

urlpatterns = [
    path("", superadmin_views.superadmin_home_view, name="home"),

    # User management
    path("users/", superadmin_views.user_list_view, name="users"),
    path("users/create/", superadmin_views.user_create_view, name="user_create"),
    path("users/<uuid:user_id>/edit/", superadmin_views.user_edit_view, name="user_edit"),
    path("users/<uuid:user_id>/resend-welcome/", superadmin_views.user_resend_welcome_email_view, name="user_resend_welcome"),
    path("users/<uuid:user_id>/toggle-status/", superadmin_views.user_toggle_status_view, name="user_toggle_status"),

    # Organization management
    path("organizations/", superadmin_views.org_list_view, name="organizations"),
    path("organizations/create/", superadmin_views.org_create_view, name="org_create"),
    path("organizations/<uuid:org_id>/", superadmin_views.org_dashboard_view, name="org_dashboard"),
    path("organizations/<uuid:org_id>/view/", superadmin_views.org_detail_view, name="org_detail"),
    path("organizations/<uuid:org_id>/edit/", superadmin_views.org_edit_view, name="org_edit"),
    path("organizations/<uuid:org_id>/delete/", superadmin_views.org_delete_view, name="org_delete"),
    path("organizations/<uuid:org_id>/resend-credentials/", superadmin_views.org_resend_credentials_view, name="org_resend_credentials"),

    # Location management
    path("locations/", superadmin_views.location_list_view, name="locations"),
    path("locations/create/", superadmin_views.location_create_view, name="location_create"),
    path("locations/<uuid:location_id>/edit/", superadmin_views.location_edit_view, name="location_edit"),
    path("locations/<uuid:location_id>/delete/", superadmin_views.location_delete_view, name="location_delete"),

    # Department and cost center management
    path("departments/create/", superadmin_views.dept_create_view, name="dept_create"),
    path("departments/<uuid:dept_id>/edit/", superadmin_views.dept_edit_view, name="dept_edit"),
    path("cost-centers/create/", superadmin_views.cost_center_create_view, name="cost_center_create"),
    path("cost-centers/<uuid:cc_id>/edit/", superadmin_views.cost_center_edit_view, name="cost_center_edit"),
    path("cost-centers/options/", superadmin_views.cost_center_options_view, name="cost_center_options"),

    # Budget management
    path("budgets/", superadmin_views.budget_list_view, name="budgets"),
    path("fiscal-periods/create/", superadmin_views.fiscal_period_create_view, name="fiscal_period_create"),
    path("fiscal-periods/<uuid:period_id>/edit/", superadmin_views.fiscal_period_edit_view, name="fiscal_period_edit"),
    path("budgets/create/", superadmin_views.budget_create_view, name="budget_create"),
    path("budgets/<uuid:budget_id>/edit/", superadmin_views.budget_edit_view, name="budget_edit"),

    # Policy management
    path("policies/", superadmin_views.policy_list_view, name="policies"),
    path("policies/create/", superadmin_views.policy_create_view, name="policy_create"),
    path("policies/<uuid:policy_id>/", superadmin_views.policy_detail_view, name="policy_detail"),
    path("policies/<uuid:policy_id>/edit/", superadmin_views.policy_edit_view, name="policy_edit"),
    path("policies/<uuid:policy_id>/duplicate/", superadmin_views.policy_duplicate_view, name="policy_duplicate"),
    path("policies/<uuid:policy_id>/toggle-status/", superadmin_views.policy_toggle_status_view, name="policy_toggle_status"),
    path("policies/<uuid:policy_id>/archive/", superadmin_views.policy_archive_view, name="policy_archive"),

    # Audit management
    path("audit/", superadmin_views.audit_list_view, name="audit"),
    path("audit/export/", superadmin_views.audit_export_view, name="audit_export"),
]

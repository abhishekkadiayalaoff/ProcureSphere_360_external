import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from django.conf import settings
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import Role, User
from apps.organization.models import Organization, Department
from apps.approvals.models import ApprovalPolicy, ApprovalStep
from apps.approvals.services import evaluate_approval_chain
from apps.contracts.permissions import CanManageContract
from apps.core.context_processors import layout_context
from apps.core.exceptions import custom_exception_handler


@pytest.mark.django_db
class TestUnitDefectRemediation:
    def test_evaluate_approval_chain_zero_steps_is_pure_read_only(self):
        """
        DEF-002 / TC-APR-022:
        Evaluating an approval policy with zero steps must return [] and NOT
        execute database write mutations (no ApprovalStep.objects.get_or_create).
        """
        org = Organization.objects.create(name="Zero Steps Org", code="ZS-ORG")
        dept = Department.objects.create(organization=org, name="Zero Steps Dept", code="ZSD")
        policy = ApprovalPolicy.objects.create(
            name="Zero Steps Test Policy",
            module=ApprovalPolicy.MODULE_PR,
            min_amount=Decimal("0.00"),
            max_amount=Decimal("10000.00"),
            department=dept,
            is_active=True,
        )
        assert policy.steps.count() == 0

        initial_step_count = ApprovalStep.objects.count()

        # Evaluate chain for this department's policy - must return empty list without creating rows in DB
        chain = evaluate_approval_chain(
            module=ApprovalPolicy.MODULE_PR,
            amount=Decimal("500.00"),
            department=dept,
        )
        assert chain == []
        assert ApprovalStep.objects.count() == initial_step_count

    def test_custom_exception_handler_sanitizes_500_in_production(self):
        """
        DEF-003:
        When settings.DEBUG is False, unhandled 500 exceptions must not expose
        internal raw exception strings (preventing CWE-209 information disclosure).
        """
        exc = RuntimeError("Secret database credentials or internal stack trace: /var/procuresphere/secret.key")
        context = {"request": MagicMock()}

        with override_settings(DEBUG=False):
            response = custom_exception_handler(exc, context)

            assert response is not None
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "error" in response.data
            assert response.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
            assert response.data["error"]["message"] == "An unexpected internal server error occurred."
            # Details must be sanitized, not containing the sensitive string
            assert "secret.key" not in response.data["error"]["details"]
            assert response.data["error"]["details"] == "An unexpected error occurred. Please contact the system administrator."

    def test_custom_exception_handler_shows_details_in_debug_mode(self):
        """
        DEF-003:
        When settings.DEBUG is True, exception details should be exposed for developer debugging.
        """
        exc = ValueError("Debug mode explicit error message")
        context = {"request": MagicMock()}

        with override_settings(DEBUG=True):
            response = custom_exception_handler(exc, context)

            assert response is not None
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert response.data["error"]["details"] == "Debug mode explicit error message"

    def test_can_manage_contract_rbac_enforcement(self):
        """
        DEF-001:
        CanManageContract strictly restricts write operations to Super Admin,
        Legal Manager, and Procurement Manager per docs/rbac_matrix.md.
        Procurement Executives, Requesters, and Vendors are strictly rejected (False).
        """
        perm = CanManageContract()
        factory = RequestFactory()
        post_request = factory.post("/api/v1/contracts/")

        # Super Admin
        sa = User(email="sa@example.com", is_superuser=True)
        post_request.user = sa
        assert perm.has_permission(post_request, None) is True

        # Legal Manager
        legal_role = Role.objects.get_or_create(code=Role.LEGAL_MGR, defaults={"name": "Legal Manager"})[0]
        legal_user = User(email="legal@example.com", role=legal_role)
        post_request.user = legal_user
        assert perm.has_permission(post_request, None) is True

        # Procurement Manager
        pm_role = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})[0]
        pm_user = User(email="pm@example.com", role=pm_role)
        post_request.user = pm_user
        assert perm.has_permission(post_request, None) is True

        # Procurement Executive (must be FALSE for unsafe/write methods)
        pe_role = Role.objects.get_or_create(code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"})[0]
        pe_user = User(email="pe@example.com", role=pe_role)
        post_request.user = pe_user
        assert perm.has_permission(post_request, None) is False

        # Requester (must be FALSE)
        req_role = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})[0]
        req_user = User(email="req@example.com", role=req_role)
        post_request.user = req_user
        assert perm.has_permission(post_request, None) is False

        # SAFE methods (GET) are allowed for authenticated users
        get_request = factory.get("/api/v1/contracts/")
        get_request.user = pe_user
        assert perm.has_permission(get_request, None) is True

    def test_layout_context_proc_exec_mapping(self):
        """
        DEF-004:
        layout_context maps PROC_EXEC to 'base.html' (which embeds proc_exec_sidebar.html).
        """
        factory = RequestFactory()
        request = factory.get("/procurement/")
        pe_role = Role.objects.get_or_create(code=Role.PROC_EXEC, defaults={"name": "Procurement Executive"})[0]
        pe_user = User(email="pe@example.com", role=pe_role)
        request.user = pe_user

        ctx = layout_context(request)
        assert ctx.get("base_layout") == "base.html"

    def test_url_namespace_uniqueness_and_login_reversal(self):
        """
        Elimination of duplicate accounts include in config/urls.py:
        Both 'login' and 'accounts:login' resolve to '/login/' without duplicate namespace warnings.
        """
        assert reverse("accounts:login") == "/login/"
        assert reverse("login") == "/login/"

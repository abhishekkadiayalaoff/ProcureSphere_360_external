import pytest
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import User


@pytest.mark.django_db
def test_all_10_seeded_users_login_via_post_request():
    call_command("seed_demo_data")

    users_to_test = [
        ("admin@procuresphere.com", "ProcureAdmin@360!"),
        ("requester01@procuresphere.com", "Requester@360!"),
        ("dept.approver01@procuresphere.com", "DeptApprover@360!"),
        ("proc.executive01@procuresphere.com", "ProcExec@360!"),
        ("proc.manager01@procuresphere.com", "ProcManager@360!"),
        ("finance.ap01@procuresphere.com", "FinanceAP@360!"),
        ("stores.recv01@procuresphere.com", "StoresRecv@360!"),
        ("legal.contract01@procuresphere.com", "LegalContract@360!"),
        ("compliance.audit01@procuresphere.com", "ComplianceAudit@360!"),
        ("vendor.user01@procuresphere.com", "VendorUser@360!"),
    ]

    for email, password in users_to_test:
        client = Client()
        response = client.post(
            "/login/",
            {"email": email, "password": password},
            follow=True,
        )
        assert response.status_code == 200, f"Failed to login {email}"
        user = User.objects.get(email=email)
        assert response.context["user"] == user, f"User session not set for {email}"

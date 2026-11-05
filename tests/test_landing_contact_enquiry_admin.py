import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.core.models import ContactEnquiry


@pytest.mark.django_db
class TestLandingContactEnquiryAdmin:
    def test_contact_form_submission_persists_to_db(self):
        """
        Public user submits the landing page contact form.
        Enquiry must be saved to PostgreSQL database as ContactEnquiry with status 'NEW'.
        """
        client = Client()
        response = client.post(
            reverse("contact_submit"),
            data={
                "name": "Aarav Patel",
                "email": "aarav.patel@example.com",
                "country_code": "+91",
                "phone": "9876543210",
                "message": "We need an enterprise procurement setup for 3 manufacturing plants.",
            },
            HTTP_USER_AGENT="Mozilla/5.0 TestBrowser",
            REMOTE_ADDR="192.168.1.50",
        )

        assert response.status_code == 200
        assert "Thank you" in response.content.decode("utf-8") or "Aarav Patel" in response.content.decode("utf-8")

        enquiry = ContactEnquiry.objects.filter(email="aarav.patel@example.com").first()
        assert enquiry is not None
        assert enquiry.name == "Aarav Patel"
        assert enquiry.country_code == "+91"
        assert enquiry.phone == "9876543210"
        assert enquiry.formatted_phone == "+91 9876543210"
        assert enquiry.status == ContactEnquiry.STATUS_NEW
        assert enquiry.message == "We need an enterprise procurement setup for 3 manufacturing plants."
        assert enquiry.user_agent == "Mozilla/5.0 TestBrowser"
        assert enquiry.ip_address == "192.168.1.50"

    def test_contact_form_invalid_input_does_not_persist(self):
        """
        Invalid submissions (bad email, mismatched phone digits) must fail validation and not persist.
        """
        client = Client()
        initial_count = ContactEnquiry.objects.count()

        # Invalid phone (only 5 digits for India)
        response = client.post(
            reverse("contact_submit"),
            data={
                "name": "Invalid User",
                "email": "invalid@example.com",
                "country_code": "+91",
                "phone": "12345",
                "message": "This is a short test message.",
            },
        )
        assert response.status_code == 200
        assert "Mobile number for" in response.content.decode("utf-8")
        assert ContactEnquiry.objects.count() == initial_count

    def test_django_admin_superadmin_can_view_and_manage_enquiries(self):
        """
        Superadmin (superadmin@procuresphere.com) logs into Django admin
        and can view the Contact Enquiry change list and details.
        """
        enquiry = ContactEnquiry.objects.create(
            name="Rohan Verma",
            email="rohan.verma@example.com",
            country_code="+91",
            phone="9123456789",
            message="Looking for vendor scorecard automation.",
        )

        sa_role = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})[0]
        superadmin = User.objects.create(
            email="superadmin_test@procuresphere.com",
            role=sa_role,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        client = Client()
        client.force_login(superadmin)

        # Admin index lists Contact Enquiry
        index_res = client.get("/admin/")
        assert index_res.status_code == 200
        assert "contactenquiry" in index_res.content.decode("utf-8").lower()

        # Contact Enquiry change list displays the record
        list_res = client.get("/admin/core/contactenquiry/")
        assert list_res.status_code == 200
        content = list_res.content.decode("utf-8")
        assert "Rohan Verma" in content
        assert "rohan.verma@example.com" in content
        assert "+91 9123456789" in content

        # Admin change detail view
        detail_res = client.get(f"/admin/core/contactenquiry/{enquiry.id}/change/")
        assert detail_res.status_code == 200
        assert "Looking for vendor scorecard automation." in detail_res.content.decode("utf-8")

        # Admin action to update status to CONTACTED
        action_res = client.post(
            "/admin/core/contactenquiry/",
            data={
                "action": "mark_as_contacted",
                "_selected_action": [str(enquiry.id)],
            },
            follow=True,
        )
        assert action_res.status_code == 200
        enquiry.refresh_from_db()
        assert enquiry.status == ContactEnquiry.STATUS_CONTACTED

    def test_unauthorized_user_cannot_access_admin_enquiries(self):
        """
        Regular users (e.g. Requester or unauthenticated) cannot access /admin/core/contactenquiry/.
        """
        req_role = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})[0]
        requester = User.objects.create(
            email="requester_test@example.com",
            role=req_role,
            is_staff=False,
            is_superuser=False,
        )

        client = Client()

        # Unauthenticated redirects to login
        res_anon = client.get("/admin/core/contactenquiry/")
        assert res_anon.status_code == 302
        assert "/login" in res_anon.url or "/admin/login" in res_anon.url

        # Non-staff requester redirects or is forbidden
        client.force_login(requester)
        res_req = client.get("/admin/core/contactenquiry/")
        assert res_req.status_code in (302, 403)


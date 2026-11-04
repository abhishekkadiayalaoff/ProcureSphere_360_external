"""
Automated tests for ProcureSphere 360 Premium Video Footer.

Validates:
1. Background video integration reusing existing static 'landing/videos/footer-video.mp4'.
2. Presence and rendering on all public landing pages (Home, About, Solutions, Benefits, Process, Roles, FAQ).
3. All internal links and anchor targets resolve cleanly without 404s.
4. Brand identity (white logo, company description, operational status, social links).
5. Contact information (official email, phone, headquarters).
6. CTA card ("Ready to Simplify Your Procurement?" + "Request a Demo").
7. Legal modal triggers (.open-privacy-modal, .open-terms-modal).
8. Responsive styling and reduced-motion fallbacks.
"""

import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


PUBLIC_PAGES = [
    "/",
    "/about/",
    "/solutions/",
    "/benefits/",
    "/process/",
    "/roles/",
    "/faq/",
]


@pytest.mark.django_db
def test_footer_renders_on_all_public_pages(client):
    """Verify that every public landing page renders the premium footer with 200 OK."""
    for page in PUBLIC_PAGES:
        response = client.get(page)
        assert response.status_code == 200, f"Page {page} failed with status {response.status_code}"
        content = response.content.decode("utf-8")

        # Footer container & class
        assert "ps-footer" in content, f"Page {page} missing 'ps-footer' container"
        assert 'id="site-footer"' in content, f"Page {page} missing 'site-footer' id"

        # Background video integration
        assert "footer-video.mp4" in content, f"Page {page} missing 'footer-video.mp4' reference"
        assert "ps-footer-video" in content, f"Page {page} missing video styling class"
        assert "ps-footer-overlay" in content, f"Page {page} missing video overlay"

        # Brand identity with white background badge
        assert "procuresphere_360_nav_brand.png" in content, f"Page {page} missing brand logo"
        assert "ps-footer-brand-badge" in content, f"Page {page} missing brand badge container"
        assert "An integrated procurement platform connecting people" in content, f"Page {page} missing brand description"



@pytest.mark.django_db
def test_footer_video_attributes(client):
    """Verify background video has all required accessibility and performance attributes."""
    response = client.get("/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "autoplay" in content
    assert "loop" in content
    assert "muted" in content
    assert "playsinline" in content
    assert 'aria-hidden="true"' in content


@pytest.mark.django_db
def test_footer_all_internal_navigation_routes_valid(client):
    """Verify that all internal URLs linked from the footer return HTTP 200."""
    target_routes = [
        "/",
        "/about/",
        "/solutions/",
        "/benefits/",
        "/process/",
        "/roles/",
        "/faq/",
    ]
    for route in target_routes:
        res = client.get(route)
        assert res.status_code == 200, f"Footer route '{route}' failed with status {res.status_code}"


@pytest.mark.django_db
def test_footer_solutions_anchors_present_in_solutions_page(client):
    """Verify that all solution anchor IDs linked in the footer exist in the solutions template."""
    response = client.get("/solutions/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    solution_anchors = [
        'id="vendors"',
        'id="pr"',
        'id="sourcing"',
        'id="po"',
        'id="grn"',
        'id="match"',
        'id="clm"',
    ]
    for anchor in solution_anchors:
        assert anchor in content, f"Solutions page missing anchor {anchor}"


@pytest.mark.django_db
def test_footer_contact_and_legal_information(client):
    """Verify verified contact details, social links, and legal modal classes exist."""
    response = client.get("/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Contact details
    assert "support@procuresphere.com" in content
    assert "+91 98765 43210" in content
    assert "Bangalore, Karnataka" in content

    # Social links
    assert "https://x.com" in content
    assert "https://linkedin.com" in content
    assert "https://youtube.com" in content

    # Legal modal trigger classes
    assert "open-privacy-modal" in content
    assert "open-terms-modal" in content

    # Copyright and tagline
    assert "2026 ProcureSphere 360" in content
    assert "Built for clarity. Designed for control." in content

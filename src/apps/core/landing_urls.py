"""
URL patterns for the public-facing landing (marketing) website.

These patterns are included in config/urls.py BEFORE apps.core.urls so that
anonymous traffic to '/' resolves to landing_home rather than the auth-gated
home_view.

URL names use the "landing_" prefix to avoid collisions with any existing or
future ERP URL names.
"""

from django.urls import path

from apps.core.landing_views import (
    about,
    benefits,
    contact_submit,
    faq,
    landing_home,
    process,
    solutions,
)

urlpatterns = [
    # Public marketing pages
    path("", landing_home, name="landing_home"),
    path("about/", about, name="landing_about"),
    path("about/<slug:section_slug>/", about, name="landing_about_section"),
    path("solutions/", solutions, name="landing_solutions"),
    path("solutions/<slug:stage_slug>/", solutions, name="landing_solutions_stage"),
    path("benefits/", benefits, name="landing_benefits"),
    path("process/", process, name="landing_process"),
    path("faq/", faq, name="landing_faq"),
    # HTMX partial endpoint for the contact / demo-request form
    path("htmx/contact/", contact_submit, name="contact_submit"),
]

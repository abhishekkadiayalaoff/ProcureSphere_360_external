from django.urls import path

from .views import (
    award_recommend_htmx_view,
    bid_portal_dashboard_view,
    bid_portal_event_view,
    evaluation_compare_htmx_view,
    evaluation_dashboard_view,
    evaluation_event_view,
    evaluation_score_htmx_view,
    negotiation_note_htmx_view,
    sourcing_action_view,
    sourcing_attachment_download_view,
    sourcing_clarifications_htmx_view,
    sourcing_create_view,
    sourcing_detail_view,
    sourcing_edit_view,
    sourcing_event_create_htmx_view,
    sourcing_events_tab_view,
    sourcing_invites_htmx_view,
    sourcing_list_view,
    sourcing_ready_prs_tab_view,
)

urlpatterns = [
    path("sourcing/bid-portal/", bid_portal_dashboard_view, name="bid_portal_dashboard"),
    path("sourcing/evaluation/", evaluation_dashboard_view, name="evaluation_dashboard"),
    path(
        "sourcing-events/<uuid:event_id>/bid-portal/",
        bid_portal_event_view,
        name="bid_portal_event",
    ),
    path(
        "sourcing-events/<uuid:event_id>/evaluation/",
        evaluation_event_view,
        name="evaluation_event",
    ),
    path("sourcing-events/", sourcing_list_view, name="sourcing_list"),
    path("sourcing-events/create/", sourcing_create_view, name="sourcing_create"),
    path("sourcing-events/<uuid:event_id>/", sourcing_detail_view, name="sourcing_detail"),
    path("sourcing-events/<uuid:event_id>/edit/", sourcing_edit_view, name="sourcing_edit"),
    path(
        "sourcing-events/<uuid:event_id>/actions/<slug:action>/",
        sourcing_action_view,
        name="sourcing_action",
    ),
    path(
        "sourcing-events/<uuid:event_id>/attachments/<uuid:attachment_id>/download/",
        sourcing_attachment_download_view,
        name="sourcing_attachment_download",
    ),
    # Procurement Executive Dashboard — Pillars 2 & 3 HTMX fragments
    path(
        "sourcing-events/htmx/ready-prs/",
        sourcing_ready_prs_tab_view,
        name="sourcing_ready_prs_tab",
    ),
    path(
        "sourcing-events/htmx/events-tab/",
        sourcing_events_tab_view,
        name="sourcing_events_tab",
    ),
    path(
        "sourcing-events/htmx/create/",
        sourcing_event_create_htmx_view,
        name="sourcing_event_create_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/invites/",
        sourcing_invites_htmx_view,
        name="sourcing_invites_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/clarifications/",
        sourcing_clarifications_htmx_view,
        name="sourcing_clarifications_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/evaluation/",
        evaluation_compare_htmx_view,
        name="evaluation_compare_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/score/",
        evaluation_score_htmx_view,
        name="evaluation_score_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/negotiate/",
        negotiation_note_htmx_view,
        name="negotiation_note_htmx",
    ),
    path(
        "sourcing-events/<uuid:event_id>/htmx/recommend-award/",
        award_recommend_htmx_view,
        name="award_recommend_htmx",
    ),
]

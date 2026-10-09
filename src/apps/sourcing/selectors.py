from .models import SourcingEvent, VendorBid


def get_all_sourcing_events():
    return (
        SourcingEvent.objects.select_related("requisition")
        .prefetch_related("invitations", "bids")
        .order_by("-created_at")
    )


def get_sourcing_event_by_id(event_id):
    return (
        SourcingEvent.objects.select_related("requisition")
        .prefetch_related("invitations", "bids")
        .filter(id=event_id)
        .first()
    )


def get_sealed_vendor_bids(event: SourcingEvent, requesting_user):
    """
    Selector that enforces sealed bid privacy controls:
    1. Vendor users see ONLY their own bids.
    2. Internal evaluators see NO bids while event is in BID_WINDOW.
    3. Once BID_WINDOW closes, evaluators see all submitted bids.
    """
    queryset = (
        VendorBid.objects.select_related("vendor", "event")
        .prefetch_related("lines")
        .filter(event=event)
    )

    if requesting_user.is_vendor:
        return queryset.filter(vendor_id=requesting_user.vendor_id)

    # Internal evaluators: block bid visibility while bid window is open
    if event.status == SourcingEvent.STATUS_BID_WINDOW:
        return VendorBid.objects.none()

    return queryset.order_by("total_bid_amount")

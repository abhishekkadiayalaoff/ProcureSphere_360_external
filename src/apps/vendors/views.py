from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Vendor


@login_required(login_url="/admin/login/")
def vendor_list_view(request):
    """
    Renders the Vendor Master list page.
    """
    vendors = Vendor.objects.select_related("category").order_by("-created_at")

    return render(
        request,
        "pages/vendors/list.html",
        {
            "vendors": vendors,
        },
    )

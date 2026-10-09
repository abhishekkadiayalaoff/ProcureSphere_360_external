from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.invoices.models import SupplierInvoice


@login_required(login_url="/admin/login/")
def list_view(request):
    items = SupplierInvoice.objects.all().order_by("-created_at")
    return render(request, "pages/invoices/list.html", {"items": items})

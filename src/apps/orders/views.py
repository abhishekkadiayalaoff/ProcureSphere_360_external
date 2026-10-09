from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.orders.models import PurchaseOrder


@login_required(login_url="/admin/login/")
def list_view(request):
    items = PurchaseOrder.objects.all().order_by("-created_at")
    return render(request, "pages/orders/list.html", {"items": items})

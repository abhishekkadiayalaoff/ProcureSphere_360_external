from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.requisitions.models import PurchaseRequisition


@login_required(login_url="/admin/login/")
def list_view(request):
    items = PurchaseRequisition.objects.all().order_by("-created_at")
    return render(request, "pages/requisitions/list.html", {"items": items})

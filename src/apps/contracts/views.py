from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.contracts.models import Contract


@login_required(login_url="/admin/login/")
def list_view(request):
    items = Contract.objects.all().order_by("-created_at")
    return render(request, "pages/contracts/list.html", {"items": items})

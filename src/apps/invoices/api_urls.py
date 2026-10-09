from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.orders.models import PurchaseOrder
from apps.vendors.models import Vendor

from .models import InvoiceLine, MatchException, SupplierInvoice
from .services import (
    create_supplier_invoice_service,
    mark_invoice_paid_service,
    resolve_match_exception_service,
    run_3_way_match_service,
)


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = "__all__"


class MatchExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchException
        fields = "__all__"


class SupplierInvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    exceptions = MatchExceptionSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = SupplierInvoice
        fields = "__all__"


class SupplierInvoiceViewSet(viewsets.ModelViewSet):
    queryset = (
        SupplierInvoice.objects.select_related("vendor", "po")
        .prefetch_related("lines", "exceptions")
        .all()
    )
    serializer_class = SupplierInvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(vendor_id=user.vendor_id)
        return self.queryset

    @action(detail=False, methods=["post"], url_path="create-invoice")
    def create_invoice(self, request):
        vendor_id = request.data.get("vendor_id")
        po_id = request.data.get("po_id")
        invoice_number = request.data.get("invoice_number")
        invoice_date = request.data.get("invoice_date")
        due_date = request.data.get("due_date")
        line_items = request.data.get("line_items", [])
        notes = request.data.get("notes", "")

        vendor = Vendor.objects.get(pk=vendor_id)
        po = PurchaseOrder.objects.get(pk=po_id)

        invoice = create_supplier_invoice_service(
            vendor=vendor,
            po=po,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            line_items=line_items,
            notes=notes,
            created_by_user=request.user,
        )
        return Response(SupplierInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="run-match")
    def run_match(self, request, pk=None):
        invoice = self.get_object()
        updated_invoice, exceptions = run_3_way_match_service(invoice=invoice, user=request.user)
        return Response(
            {
                "invoice": SupplierInvoiceSerializer(updated_invoice).data,
                "exceptions_count": len(exceptions),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="pay")
    def pay_invoice(self, request, pk=None):
        invoice = self.get_object()
        paid_invoice = mark_invoice_paid_service(invoice=invoice, user=request.user)
        return Response(SupplierInvoiceSerializer(paid_invoice).data, status=status.HTTP_200_OK)


class MatchExceptionViewSet(viewsets.ModelViewSet):
    queryset = MatchException.objects.select_related("invoice", "resolved_by").all()
    serializer_class = MatchExceptionSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve_exception(self, request, pk=None):
        exception = self.get_object()
        notes = request.data.get("resolution_notes", "Resolved by Finance")
        action_type = request.data.get("action", "RESOLVE")
        resolved = resolve_match_exception_service(
            match_exception=exception,
            resolved_by_user=request.user,
            resolution_notes=notes,
            action=action_type,
        )
        return Response(MatchExceptionSerializer(resolved).data, status=status.HTTP_200_OK)


router = DefaultRouter()
router.register(r"exceptions", MatchExceptionViewSet, basename="match-exception")
router.register(r"", SupplierInvoiceViewSet, basename="invoice")

urlpatterns = router.urls

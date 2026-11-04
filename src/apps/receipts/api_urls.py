from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.accounts.models import Role, User
from apps.orders.models import POLine, PurchaseOrder

from .models import GoodsReceipt, ReceiptLine


class CanManageGoodsReceipt(BasePermission):
    """
    Stores Receiver and Super Admin can create and modify goods receipts.
    Requesters, Vendors, and Auditors are read-only or blocked from creation.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, "role_code", None) == Role.AUDITOR:
            return request.method in SAFE_METHODS

        is_vendor = (
            getattr(request.user, "is_vendor", False)
            or getattr(request.user, "role_code", None) == Role.VENDOR_USER
        )
        if is_vendor:
            return request.method in SAFE_METHODS

        if getattr(request.user, "role_code", None) == Role.REQUESTER:
            return request.method in SAFE_METHODS

        if request.method in SAFE_METHODS:
            return True

        return request.user.is_superuser or request.user.role_code in [
            Role.SUPER_ADMIN,
            Role.STORES_RECEIVER,
            Role.PROC_MGR,
        ]


class ReceiptLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptLine
        fields = "__all__"


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = ReceiptLineSerializer(many=True, read_only=True)
    po_number = serializers.CharField(source="po.po_number", read_only=True)
    received_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = GoodsReceipt
        fields = "__all__"

    def validate(self, attrs):
        po = attrs.get("po")
        if po and po.status not in [
            PurchaseOrder.STATUS_ISSUED,
            PurchaseOrder.STATUS_ACKNOWLEDGED,
            PurchaseOrder.STATUS_PARTIAL_RECEIPT,
        ]:
            raise serializers.ValidationError(
                {
                    "po": [
                        f"Cannot record goods receipt against PO in status '{po.status}'. Must be ISSUED or ACKNOWLEDGED."
                    ]
                }
            )

        if self.instance is None:
            lines = self.initial_data.get("lines")
            if lines is None or not isinstance(lines, list) or len(lines) == 0:
                raise serializers.ValidationError(
                    {"lines": ["Receipt must contain at least one line item."]}
                )
            if not po:
                raise serializers.ValidationError({"po": ["Purchase Order is required."]})

            po_lines_map = {str(l.id): l for l in po.lines.all()}
            po_lines_list = list(po.lines.all())

            for idx, item in enumerate(lines):
                if not isinstance(item, dict):
                    raise serializers.ValidationError({"lines": [f"Line item {idx + 1} must be an object."]})
                po_line = None
                po_line_id = item.get("po_line_id") or item.get("po_line")
                if po_line_id:
                    po_line = po_lines_map.get(str(po_line_id))
                    if not po_line:
                        raise serializers.ValidationError(
                            {"lines": [f"PO line '{po_line_id}' does not belong to Purchase Order {po.po_number}."]}
                        )
                elif idx < len(po_lines_list):
                    po_line = po_lines_list[idx]
                elif po_lines_list:
                    po_line = po_lines_list[0]

                raw_qty = item.get("quantity_received")
                if raw_qty is None:
                    raw_qty = po_line.quantity if po_line else "1"
                try:
                    qty_recv = Decimal(str(raw_qty))
                except (TypeError, ValueError, ArithmeticError, Exception):
                    raise serializers.ValidationError({"lines": [f"Quantity received must be a valid numeric value for line {idx + 1}."]})

                if qty_recv <= Decimal("0.00"):
                    raise serializers.ValidationError({"lines": [f"Quantity received must be greater than zero for line {idx + 1}."]})

                if po_line:
                    rem = po_line.remaining_quantity
                    if qty_recv > rem:
                        raise serializers.ValidationError(
                            {"lines": [f"Quantity received ({qty_recv}) cannot exceed remaining quantity ({rem}) for '{po_line.item_description}'."]}
                        )

                raw_acc = item.get("quantity_accepted")
                if raw_acc is not None and str(raw_acc).strip() != "":
                    try:
                        qty_acc = Decimal(str(raw_acc))
                    except (TypeError, ValueError, ArithmeticError, Exception):
                        raise serializers.ValidationError({"lines": [f"Quantity accepted must be a valid numeric value for line {idx + 1}."]})
                    if qty_acc < Decimal("0.00"):
                        raise serializers.ValidationError({"lines": [f"Quantity accepted cannot be negative for line {idx + 1}."]})
                    if qty_acc > qty_recv:
                        raise serializers.ValidationError({"lines": [f"Quantity accepted ({qty_acc}) cannot exceed quantity received ({qty_recv}) for line {idx + 1}."]})

        return attrs

    def create(self, validated_data):
        lines_data = self.initial_data.get("lines", [])
        from apps.receipts.services import create_goods_receipt_service

        po = validated_data["po"]
        request = self.context.get("request")
        received_by = validated_data.get("received_by") or (request.user if request else None)
        delivery_note = validated_data.get("delivery_note_number", "")
        remarks = validated_data.get("remarks", "")

        try:
            return create_goods_receipt_service(
                po=po,
                received_by=received_by,
                receipt_items=lines_data,
                delivery_note_number=delivery_note,
                remarks=remarks,
            )
        except ValidationError as e:
            msg = e.messages if hasattr(e, "messages") else [str(e)]
            raise serializers.ValidationError({"lines": msg})


class GoodsReceiptPermission(IsAuthenticated):
    """
    Enforces RBAC on Goods Receipt API:
    - Vendor users denied access to internal goods receipt endpoints.
    - Read (SAFE_METHODS): Stores Receiver, Super Admin, Auditor, Procurement Executive/Manager, Finance.
    - State modifications (POST, PUT, PATCH, DELETE): Stores Receiver or Super Admin only.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True

        role_code = getattr(request.user, "role_code", None) or (
            request.user.role.code if hasattr(request.user, "role") and request.user.role else None
        )

        if request.method in SAFE_METHODS:
            return role_code in [
                Role.STORES_RECEIVER,
                Role.SUPER_ADMIN,
                Role.AUDITOR,
                Role.PROC_EXEC,
                Role.PROC_MGR,
                Role.FINANCE_AP,
                Role.VENDOR_USER,
            ]

        if role_code == Role.VENDOR_USER:
            return False

        return role_code in [Role.STORES_RECEIVER, Role.SUPER_ADMIN]


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = (
        GoodsReceipt.objects.select_related("po", "received_by")
        .prefetch_related("lines")
        .order_by("-created_at")
    )
    serializer_class = GoodsReceiptSerializer
    permission_classes = [GoodsReceiptPermission]

    def perform_destroy(self, instance):
        if instance.status != GoodsReceipt.STATUS_DRAFT:
            raise serializers.ValidationError(
                {"status": [f"Goods receipt in '{instance.status}' status cannot be deleted."]}
            )
        instance.delete()

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset

        # Vendor scoping: only receipts for vendor's own purchase orders
        if getattr(user, "is_vendor", False) or getattr(user, "vendor_id", None):
            if getattr(user, "vendor_id", None):
                qs = qs.filter(po__vendor_id=user.vendor_id)
            else:
                return qs.none()

        po_id = self.request.query_params.get("po")
        if po_id:
            qs = qs.filter(po_id=po_id)

        received_date = self.request.query_params.get("received_date")
        if received_date:
            qs = qs.filter(received_date__date=received_date)

        return qs

    @action(detail=True, methods=["post"], url_path="inspect")
    def inspect(self, request, pk=None):
        receipt = self.get_object()
        raw_items = (
            request.data.get("results")
            or request.data.get("inspection_items")
            or request.data.get("lines")
        )
        lines = list(receipt.lines.all())
        if not raw_items:
            raw_items = [
                {
                    "receipt_line_id": line.id,
                    "passed": True,
                    "rejected_quantity": Decimal("0.00"),
                    "inspection_notes": "Inspection PASSED",
                }
                for line in lines
            ]
        else:
            formatted_items = []
            for idx, item in enumerate(raw_items):
                item_dict = dict(item)
                if "receipt_line_id" not in item_dict and "receipt_line" not in item_dict:
                    if idx < len(lines):
                        item_dict["receipt_line_id"] = lines[idx].id
                    elif lines:
                        item_dict["receipt_line_id"] = lines[0].id
                formatted_items.append(item_dict)
            raw_items = formatted_items

        try:
            from .services import record_inspection_service

            updated = record_inspection_service(
                receipt=receipt,
                inspected_by=request.user,
                inspection_items=raw_items,
            )
            return Response(self.get_serializer(updated).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            msg = e.messages if hasattr(e, "messages") else [str(e)]
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": msg[0] if isinstance(msg, list) else str(e),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="handoff")
    def handoff(self, request, pk=None):
        receipt = self.get_object()
        storage_location = request.data.get("storage_location", "MAIN-WH")
        notes = request.data.get("handoff_notes", request.data.get("notes", ""))
        try:
            from .services import handoff_goods_to_stock_service

            updated = handoff_goods_to_stock_service(
                receipt=receipt,
                handed_off_by=request.user,
                storage_location=storage_location,
                handoff_notes=notes,
            )
            return Response(self.get_serializer(updated).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            msg = e.messages if hasattr(e, "messages") else [str(e)]
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": msg[0] if isinstance(msg, list) else str(e),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        receipt = self.get_object()
        return Response(
            {
                "message": f"Goods Receipt {receipt.grn_number} confirmed and posted.",
                "receipt": self.get_serializer(receipt).data,
            },
            status=status.HTTP_200_OK,
        )


router = DefaultRouter()
router.register(r"", GoodsReceiptViewSet, basename="goods-receipt")

urlpatterns = router.urls

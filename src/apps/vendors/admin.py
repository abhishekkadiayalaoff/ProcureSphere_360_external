from django.contrib import admin

from .models import Vendor, VendorCategory, VendorContact, VendorDocument, VendorRiskRecord


@admin.register(VendorCategory)
class VendorCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "description", "created_at")
    search_fields = ("name", "code")


@admin.register(VendorDocument)
class VendorDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "vendor", "document_type", "is_verified", "expiry_date", "created_at")
    list_filter = ("document_type", "is_verified")
    search_fields = ("title", "vendor__legal_name", "vendor__vendor_number")


class VendorDocumentInline(admin.TabularInline):
    model = VendorDocument
    extra = 0
    fields = ("title", "document_type", "file", "is_verified", "expiry_date")


class VendorContactInline(admin.TabularInline):
    model = VendorContact
    extra = 0


class VendorRiskRecordInline(admin.TabularInline):
    model = VendorRiskRecord
    extra = 0
    readonly_fields = ("created_at", "assessed_by")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "vendor_number",
        "legal_name",
        "trade_name",
        "tax_identification_number",
        "category",
        "status",
        "email",
        "phone",
        "created_at",
    )
    list_filter = ("status", "category")
    search_fields = (
        "legal_name",
        "trade_name",
        "vendor_number",
        "tax_identification_number",
        "email",
    )
    inlines = [VendorContactInline, VendorDocumentInline, VendorRiskRecordInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(VendorContact)
class VendorContactAdmin(admin.ModelAdmin):
    list_display = ("vendor", "first_name", "last_name", "email", "phone", "is_primary")
    search_fields = ("first_name", "last_name", "email", "vendor__legal_name")


@admin.register(VendorRiskRecord)
class VendorRiskRecordAdmin(admin.ModelAdmin):
    list_display = ("vendor", "risk_level", "assessed_by", "created_at")
    list_filter = ("risk_level",)
    search_fields = ("vendor__legal_name", "vendor__vendor_number", "assessment_notes")

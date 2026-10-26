from django.contrib import admin

from .models import CostCenter, Department, FiscalPeriod, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tax_identifier", "is_active", "created_at")
    search_fields = ("name", "code")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "code")


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "manager")
    list_filter = ("department",)
    search_fields = ("code", "name")


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "year",
        "period_number",
        "start_date",
        "end_date",
        "is_closed",
    )
    list_filter = ("organization", "year", "is_closed")

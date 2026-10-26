from django.contrib import admin

from apps.contracts.models import (
    Contract,
    ContractAlert,
    ContractMilestone,
    ContractVersion,
)


class ContractVersionInline(admin.TabularInline):
    model = ContractVersion
    extra = 0


class ContractMilestoneInline(admin.TabularInline):
    model = ContractMilestone
    extra = 1


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "contract_number",
        "title",
        "version",
        "vendor",
        "status",
        "contract_value",
        "start_date",
        "end_date",
        "contract_owner",
    )
    list_filter = ("status", "vendor")
    search_fields = (
        "contract_number",
        "title",
        "vendor__legal_name",
    )
    inlines = [ContractVersionInline, ContractMilestoneInline]


@admin.register(ContractAlert)
class ContractAlertAdmin(admin.ModelAdmin):
    list_display = (
        "contract",
        "alert_type",
        "triggered_at",
        "is_processed",
    )
    list_filter = ("alert_type", "is_processed")
    search_fields = ("contract__contract_number", "message")


admin.site.register(ContractVersion)
admin.site.register(ContractMilestone)

from django.contrib import admin

from .models import ApprovalAction, ApprovalDelegate, ApprovalPolicy, ApprovalStep


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0


@admin.register(ApprovalPolicy)
class ApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "module",
        "department",
        "min_amount",
        "max_amount",
        "is_active",
        "created_at",
    )
    list_filter = ("module", "is_active", "department")
    search_fields = ("name",)
    inlines = [ApprovalStepInline]


@admin.register(ApprovalStep)
class ApprovalStepAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "step_number",
        "approver_role",
        "specific_approver",
    )
    list_filter = ("approver_role",)


@admin.register(ApprovalAction)
class ApprovalActionAdmin(admin.ModelAdmin):
    list_display = (
        "target_model_name",
        "target_object_id",
        "actor",
        "action",
        "previous_state",
        "new_state",
        "comments",
        "created_at",
    )
    list_filter = ("action", "target_model_name")
    search_fields = (
        "actor__email",
        "target_model_name",
        "target_object_id",
        "comments",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(ApprovalDelegate)
class ApprovalDelegateAdmin(admin.ModelAdmin):
    list_display = (
        "approver",
        "delegate",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("approver__email", "delegate__email")

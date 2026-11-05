from django.contrib import admin

from .admin_site import RoleBasedModelAdmin, register_model
from .models import ContactEnquiry


@admin.register(ContactEnquiry)
class ContactEnquiryAdmin(RoleBasedModelAdmin):
    """
    Django Admin interface for viewing, triaging, and managing landing page contact enquiries.
    Accessible to Super Admins and staff via /admin/core/contactenquiry/.
    """

    list_display = (
        "name",
        "email",
        "formatted_phone",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "country_code",
        "created_at",
    )
    search_fields = (
        "name",
        "email",
        "phone",
        "message",
        "notes",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "ip_address",
        "user_agent",
    )
    ordering = ("-created_at",)
    list_editable = ("status",)
    date_hierarchy = "created_at"
    actions = ["mark_as_contacted", "mark_as_resolved", "mark_as_spam"]

    fieldsets = (
        (
            "Contact Details",
            {
                "fields": (
                    "name",
                    "email",
                    ("country_code", "phone"),
                ),
            },
        ),
        (
            "Enquiry Message",
            {
                "fields": ("message",),
            },
        ),
        (
            "Triage Status & Internal Notes",
            {
                "fields": (
                    "status",
                    "notes",
                ),
            },
        ),
        (
            "Audit & Technical Metadata",
            {
                "fields": (
                    "id",
                    "ip_address",
                    "user_agent",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.action(description="Mark selected enquiries as Contacted")
    def mark_as_contacted(self, request, queryset):
        count = queryset.update(status=ContactEnquiry.STATUS_CONTACTED)
        self.message_user(request, f"{count} enquiry/enquiries marked as Contacted.")

    @admin.action(description="Mark selected enquiries as Resolved")
    def mark_as_resolved(self, request, queryset):
        count = queryset.update(status=ContactEnquiry.STATUS_RESOLVED)
        self.message_user(request, f"{count} enquiry/enquiries marked as Resolved.")

    @admin.action(description="Mark selected enquiries as Spam")
    def mark_as_spam(self, request, queryset):
        count = queryset.update(status=ContactEnquiry.STATUS_SPAM)
        self.message_user(request, f"{count} enquiry/enquiries marked as Spam.")


# Safely register to ProcureSphere custom admin_site as well
register_model(ContactEnquiry, ContactEnquiryAdmin)


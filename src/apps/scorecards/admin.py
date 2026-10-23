from apps.core.admin_site import RoleBasedModelAdmin, register_model
from apps.scorecards.models import VendorScorecard


class VendorScorecardAdmin(RoleBasedModelAdmin):
    list_display = (
        "vendor",
        "evaluation_period",
        "composite_score",
        "delivery_score",
        "quality_score",
        "price_score",
        "compliance_score",
        "evaluated_by",
    )
    list_filter = ("evaluation_period", "vendor")
    search_fields = ("vendor__legal_name", "evaluator_comments")


register_model(VendorScorecard, VendorScorecardAdmin)

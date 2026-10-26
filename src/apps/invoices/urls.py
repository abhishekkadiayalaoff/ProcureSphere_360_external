from django.urls import path

from . import views

urlpatterns = [
    path("invoices/", views.list_view, name="invoices_list"),
    path("", views.list_view, name="invoices_list_root"),
    path("settings/tolerances/", views.tolerance_settings_view, name="tolerance_settings"),
    path("create/", views.create_invoice_view, name="create_invoice"),
    path("exceptions/", views.exceptions_list_view, name="exceptions_list"),
    path("exceptions/<str:exception_id>/", views.exception_detail_view, name="exception_detail"),
    path(
        "exceptions/<str:exception_id>/resolve/",
        views.resolve_exception_view,
        name="resolve_exception",
    ),
    path("ready/", views.ready_for_payment_view, name="ready_list"),
    path("ready/<str:invoice_id>/pay/", views.pay_invoice_view, name="pay_invoice"),
    path("<str:invoice_id>/", views.invoice_detail_view, name="invoice_detail"),
]

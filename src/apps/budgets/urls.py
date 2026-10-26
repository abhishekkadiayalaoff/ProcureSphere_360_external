from django.urls import path

from . import views

urlpatterns = [
    path("", views.list_view, name="budgets_list"),
    path("ledger/", views.ledger_view, name="budgets_ledger"),
    path("exceptions/", views.budget_exceptions_view, name="budget_exceptions"),
]

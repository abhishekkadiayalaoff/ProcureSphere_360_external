from django.urls import path
from . import views

urlpatterns = [
    path("", views.list_view, name="contracts_list"),
]

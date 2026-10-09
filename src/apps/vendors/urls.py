from django.urls import path
from . import views

urlpatterns = [
    path("", views.vendor_list_view, name="vendor_list"),
]

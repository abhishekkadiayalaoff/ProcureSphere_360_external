from django.urls import path

from .views import login_page_view, logout_page_view

urlpatterns = [
    path("login/", login_page_view, name="login"),
    path("logout/", logout_page_view, name="logout"),
]

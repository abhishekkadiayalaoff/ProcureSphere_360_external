from .models import Role, User


def get_all_users():
    return User.objects.select_related("role", "department", "vendor").order_by("-date_joined")


def get_user_by_id(user_id):
    return User.objects.select_related("role", "department", "vendor").filter(id=user_id).first()


def get_all_roles():
    return Role.objects.all().order_by("name")

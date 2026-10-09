from django.db import transaction

from .models import Role, User


@transaction.atomic
def create_user_service(
    *, email, password, first_name="", last_name="", role=None, department=None, vendor=None
):
    """
    Service layer function to create a new user with proper password hashing and atomic transaction.
    """
    user = User(
        email=email,
        username=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        department=department,
        vendor=vendor,
    )
    user.set_password(password)
    user.save()
    return user


@transaction.atomic
def update_user_role_service(*, user: User, new_role: Role):
    """
    Updates user assigned role safely within a database transaction.
    """
    user.role = new_role
    user.save(update_fields=["role"])
    return user

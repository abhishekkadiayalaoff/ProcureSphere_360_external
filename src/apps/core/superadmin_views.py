import csv

import json

from functools import wraps

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role, User
from apps.accounts.password_utils import generate_secure_password
from apps.approvals.models import ApprovalPolicy
from apps.audit.models import AuditLog
from apps.budgets.models import Budget
from apps.core.superadmin_forms import (
    BudgetAdminForm,
    CostCenterAdminForm,
    DepartmentAdminForm,
    FiscalPeriodAdminForm,
    LocationAdminForm,
    OrganizationAdminForm,
    PolicyAdminForm,
    UserAdminForm,
)
from apps.notifications.email_service import send_user_welcome_email
from apps.organization.models import CostCenter, Department, FiscalPeriod, Location, Organization


@login_required

def superadmin_home_view(request):

    """Same Super Admin dashboard as the home page, served at /superadmin/."""

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    from apps.core.views import home_view



    return home_view(request)





def _is_super_admin(user):

    return user.is_authenticated and (

        user.is_superuser

        or getattr(user, "role_code", None) in [Role.SUPER_ADMIN, "ADMIN"]
        or (hasattr(user, "role") and user.role and user.role.code in [Role.SUPER_ADMIN, "ADMIN"])

    )





def super_admin_required(view_func):

    @wraps(view_func)

    def _wrapped(request, *args, **kwargs):

        if not _is_super_admin(request.user):

            return HttpResponse(

                "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

                status=403,

            )

        return view_func(request, *args, **kwargs)



    return _wrapped





def get_user_scoped_org(user):

    """

    Returns the organization to which this user is scoped.

    If the user has an effective_organization, they are strictly scoped to that organization.

    Returns None only for global platform superusers without an assigned organization.

    """

    if not user or not user.is_authenticated:

        return None

    effective_org = getattr(user, "effective_organization", None)

    if effective_org:

        return effective_org

    return None





@login_required

def user_list_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    q = request.GET.get("q", "").strip()

    role_filter = request.GET.get("role", "").strip()

    status_filter = request.GET.get("status", "").strip()



    users = User.objects.select_related("role", "department", "cost_center").all()

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        users = users.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org))



    if q:

        users = users.filter(

            Q(email__icontains=q)

            | Q(first_name__icontains=q)

            | Q(last_name__icontains=q)

            | Q(department__name__icontains=q)

            | Q(cost_center__code__icontains=q)

            | Q(role__name__icontains=q)

        )

    if role_filter:

        users = users.filter(role__code=role_filter)

    if status_filter == "active":

        users = users.filter(is_active=True)

    elif status_filter == "disabled":

        users = users.filter(is_active=False)



    users = users.order_by("-date_joined")

    roles = Role.objects.all().order_by("name")



    return render(

        request,

        "pages/dashboards/superadmin/users.html",

        {

            "users": users,

            "roles": roles,

            "q": q,

            "role_filter": role_filter,

            "status_filter": status_filter,

            "total_count": users.count(),

        },

    )





def _should_send_welcome_email(request, default=True):

    """

    Determines whether a credentials/welcome email should be dispatched.

    If 'send_welcome_email_present' is in request.POST, the UI explicitly rendered

    the toggle, so send_welcome_email must be checked (in request.POST).

    If 'send_welcome_email' is explicitly in request.POST without the hidden tag

    (e.g. from programmatic tests or API payloads), evaluate its truthiness.

    Otherwise (e.g. older payloads or automated tests omitting the field), return default.

    """

    if "send_welcome_email_present" in request.POST:

        return "send_welcome_email" in request.POST

    if "send_welcome_email" in request.POST:

        val = request.POST.get("send_welcome_email")

        return str(val).lower() in ("1", "true", "on", "yes")

    return default





@login_required

def user_create_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    if request.method == "POST":

        form = UserAdminForm(request.POST, request=request)

        if form.is_valid():

            with transaction.atomic():

                user = form.save(commit=False)

                user.username = form.cleaned_data["email"]

                user.must_change_password = True

                scoped_org = get_user_scoped_org(request.user)

                if scoped_org:

                    user.organization = scoped_org



                raw_password = form.cleaned_data.get("password")

                if not raw_password:

                    raw_password = generate_secure_password()

                user.set_password(raw_password)

                user.save()



                from apps.audit.services import create_audit_log_service



                create_audit_log_service(

                    actor=request.user,

                    action=AuditLog.ACTION_CREATE,

                    target_model="User",

                    target_object_id=str(user.id),

                    previous_state=None,

                    new_state={

                        "email": user.email,

                        "phone_number": user.phone_number,

                        "role": user.role.code if user.role else None,

                        "department": user.department.code if user.department else None,

                        "cost_center": user.cost_center.code if user.cost_center else None,

                        "is_active": user.is_active,

                        "must_change_password": user.must_change_password,

                    },

                    ip_address=request.META.get("REMOTE_ADDR"),

                    user_agent=request.META.get("HTTP_USER_AGENT", ""),

                )



            send_email_flag = _should_send_welcome_email(request, default=True)

            if send_email_flag:

                # Trigger welcome email strictly after database commit

                email_status, email_error = send_user_welcome_email(

                    user=user,

                    temporary_password=raw_password,

                    request=request,

                )



                # User-facing notifications per Section 6 specification

                messages.success(request, f"User '{user.email}' created successfully. Login credentials sent to {user.email} via Brevo.")
            else:
                messages.success(request, f"User '{user.email}' created successfully.")

            response = HttpResponse("<script>window.location.reload();</script>")
            response["HX-Refresh"] = "true"
            return response

    else:

        form = UserAdminForm(request=request, initial={"is_active": True, "send_welcome_email": True})

    return render(request, "pages/dashboards/superadmin/user_form.html", {"form": form, "is_edit": False})





@login_required

def user_edit_view(request, user_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    user = get_object_or_404(User, pk=user_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        user_org_id = user.organization_id or (user.department.organization_id if user.department else None)

        if user_org_id != scoped_org.id:

            return HttpResponse(

                "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify users from another organization.</div>",

                status=403,

            )



    if request.method == "POST":

        old_state = {

            "email": user.email,

            "phone_number": user.phone_number,

            "role": user.role.code if user.role else None,

            "department": user.department.code if user.department else None,

            "cost_center": user.cost_center.code if user.cost_center else None,

            "is_active": user.is_active,

        }

        form = UserAdminForm(request.POST, instance=user, request=request)

        if form.is_valid():

            user = form.save(commit=False)

            user.username = form.cleaned_data["email"]

            send_email_flag = _should_send_welcome_email(request, default=True)

            new_password = form.cleaned_data.get("password")
            if new_password and new_password.strip():
                raw_pwd = new_password.strip()
                user.set_password(raw_pwd)
                user.must_change_password = True
                user.save()
                send_email_flag = _should_send_welcome_email(request, default=True)
                if send_email_flag:
                    email_status, email_error = send_user_welcome_email(
                        user=user,
                        temporary_password=raw_pwd,
                        request=request,
                    )
                    if email_status == "SENT":
                        messages.info(request, f"Updated credentials email successfully sent to {user.email}.")
                    elif email_status == "QUEUED":
                        messages.info(request, f"Updated credentials email queued for delivery to {user.email}.")
                    else:
                        messages.warning(request, f"Credentials updated, but email could not be delivered: {email_error}")
            elif request.POST.get("send_welcome_email") in ["on", "true", "1"] and not request.POST.get("send_welcome_email_present"):
                raw_pwd = generate_secure_password()
                user.set_password(raw_pwd)
                user.must_change_password = True
                user.save()
                email_status, email_error = send_user_welcome_email(
                    user=user,
                    temporary_password=raw_pwd,
                    request=request,
                )
                if email_status == "SENT":
                    messages.info(request, f"Updated credentials email successfully sent to {user.email}.")
                elif email_status == "QUEUED":
                    messages.info(request, f"Updated credentials email queued for delivery to {user.email}.")
                else:
                    messages.warning(request, f"Credentials updated, but email could not be delivered: {email_error}")
            else:
                user.save()



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_UPDATE,

                target_model="User",

                target_object_id=str(user.id),

                previous_state=old_state,

                new_state={

                    "email": user.email,

                    "phone_number": user.phone_number,

                    "role": user.role.code if user.role else None,

                    "department": user.department.code if user.department else None,

                    "cost_center": user.cost_center.code if user.cost_center else None,

                    "is_active": user.is_active,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            status_str = "Active" if user.is_active else "Disabled"
            messages.success(request, f"User '{user.email}' updated successfully ({status_str}).")

            response = HttpResponse("<script>window.location.reload();</script>")
            response["HX-Refresh"] = "true"
            return response

    else:

        form = UserAdminForm(instance=user, request=request)

    return render(request, "pages/dashboards/superadmin/user_form.html", {"form": form, "is_edit": True, "user_obj": user})





@login_required

def user_resend_welcome_email_view(request, user_id):

    """

    Super Admin action to safely retry or resend the welcome email with a refreshed

    temporary password.

    """

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    user = get_object_or_404(User, pk=user_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        user_org_id = user.organization_id or (user.department.organization_id if user.department else None)

        if user_org_id != scoped_org.id:

            return HttpResponse(

                "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify users from another organization.</div>",

                status=403,

            )



    if request.method == "POST":

        new_temp_pwd = generate_secure_password()

        user.set_password(new_temp_pwd)

        user.must_change_password = True

        user.save(update_fields=["password", "must_change_password"])



        from apps.audit.services import create_audit_log_service



        create_audit_log_service(

            actor=request.user,

            action=AuditLog.ACTION_UPDATE,

            target_model="User",

            target_object_id=str(user.id),

            previous_state={"welcome_email_resend": False},

            new_state={"welcome_email_resend": True, "email": user.email},

            ip_address=request.META.get("REMOTE_ADDR"),

            user_agent=request.META.get("HTTP_USER_AGENT", ""),

        )



        email_status, email_error = send_user_welcome_email(

            user=user,

            temporary_password=new_temp_pwd,

            request=request,

        )



        if email_status == "SENT":

            messages.success(request, f"Welcome email sent successfully to {user.email}.")

        elif email_status == "QUEUED":

            messages.info(request, "Welcome email queued for delivery.")

        else:

            messages.warning(

                request,

                f"Could not deliver welcome email to {user.email}. Please retry.",

            )



        return HttpResponse("<script>window.location.reload();</script>")

    return HttpResponse(status=405)





@login_required

def cost_center_options_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse("<option value=''>-- Unauthorized --</option>", status=403)

    dept_id = request.GET.get("department", "").strip()

    cost_centers = CostCenter.objects.none()

    if dept_id:

        try:

            import uuid

            uuid.UUID(dept_id)

            cost_centers = CostCenter.objects.filter(department_id=dept_id)

            scoped_org = get_user_scoped_org(request.user)

            if scoped_org:

                cost_centers = cost_centers.filter(department__organization=scoped_org)

            cost_centers = cost_centers.order_by("name")

        except (ValueError, AttributeError):

            pass

    return render(

        request,

        "pages/dashboards/superadmin/cost_center_options.html",

        {"cost_centers": cost_centers},

    )



def org_list_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        orgs = Organization.objects.select_related("admin_user").filter(id=scoped_org.id)

        departments = Department.objects.select_related("organization").filter(organization=scoped_org).order_by("name")

        cost_centers = (

            CostCenter.objects.select_related("department", "manager")

            .filter(department__organization=scoped_org)

            .prefetch_related(

                Prefetch(

                    "requester_users",

                    queryset=User.objects.order_by("email"),

                )

            )

            .order_by("code")

        )

    else:

        orgs = Organization.objects.select_related("admin_user").all().order_by("name")

        departments = Department.objects.select_related("organization").all().order_by("name")

        cost_centers = (

            CostCenter.objects.select_related("department", "manager")

            .prefetch_related(

                Prefetch(

                    "requester_users",

                    queryset=User.objects.order_by("email"),

                )

            )

            .order_by("code")

        )

    selected_dept = request.GET.get("department", "").strip()

    if selected_dept:

        try:

            import uuid

            uuid.UUID(selected_dept)

            cost_centers = cost_centers.filter(department_id=selected_dept)

        except (ValueError, AttributeError):

            selected_dept = ""



    return render(

        request,

        "pages/dashboards/superadmin/organizations.html",

        {

            "orgs": orgs,

            "departments": departments,

            "cost_centers": cost_centers,

            "selected_dept": selected_dept,

            "is_superuser": request.user.is_superuser and not scoped_org,

            "scoped_org": scoped_org,

        },

    )





@login_required

@super_admin_required

def org_create_view(request):

    scoped_org = get_user_scoped_org(request.user)

    if not _is_super_admin(request.user) or scoped_org is not None or not request.user.is_superuser:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Only platform administrators without an assigned organization can register new legal entities.</div>",

            status=403,

        )



    if request.method == "POST":

        form = OrganizationAdminForm(request.POST)

        if form.is_valid():

            from apps.organization.services import create_organization_with_admin_service



            admin_user_obj = form.cleaned_data.get("admin_user")

            admin_email = (form.cleaned_data.get("admin_email") or "").strip()

            if admin_user_obj and not admin_email:

                admin_email = admin_user_obj.email

            admin_first_name = form.cleaned_data.get("admin_first_name", "")

            admin_last_name = form.cleaned_data.get("admin_last_name", "")

            admin_password = form.cleaned_data.get("admin_password")

            send_welcome_flag = bool(form.cleaned_data.get("send_welcome_email", False))

            try:
                org, admin_user, raw_pwd = create_organization_with_admin_service(
                    name=form.cleaned_data["name"],
                    code=form.cleaned_data["code"],
                    tax_identifier=form.cleaned_data.get("tax_identifier", ""),
                    address=form.cleaned_data.get("address", ""),
                    is_active=form.cleaned_data.get("is_active", True),
                    admin_email=admin_email,
                    admin_first_name=admin_first_name,
                    admin_last_name=admin_last_name,
                    admin_password=admin_password,
                    proc_mgr_email=form.cleaned_data.get("proc_mgr_email"),
                    proc_mgr_first_name=form.cleaned_data.get("proc_mgr_first_name", ""),
                    proc_mgr_last_name=form.cleaned_data.get("proc_mgr_last_name", ""),
                    proc_mgr_password=form.cleaned_data.get("proc_mgr_password"),
                    auditor_email=form.cleaned_data.get("auditor_email"),
                    auditor_first_name=form.cleaned_data.get("auditor_first_name", ""),
                    auditor_last_name=form.cleaned_data.get("auditor_last_name", ""),
                    auditor_password=form.cleaned_data.get("auditor_password"),
                    send_welcome_email_flag=send_welcome_flag,
                    request=request,
                    actor=request.user,
                )
            except ValidationError as val_err:
                form.add_error("admin_email", str(val_err))
                err_msg = "This user does not belong to this organization."
                form.add_error("admin_email", err_msg)
                messages.error(request, err_msg)
                return render(request, "pages/dashboards/superadmin/org_form.html", {"form": form, "is_edit": False})

            if form.cleaned_data.get("import_standard_vendors", False):
                from apps.vendors.services import import_standard_vendors_for_org_service
                try:
                    count, msg = import_standard_vendors_for_org_service(org, actor=request.user)
                    if count > 0:
                        messages.info(request, f"Provisioned {count} approved vendor records into '{org.name}'.")
                except Exception as vendor_import_err:
                    import logging
                    logging.getLogger(__name__).warning("Standard vendor auto-import failed: %s", vendor_import_err)

            admin_info = f" with Administrator '{admin_user.email}'" if admin_user else ""

            messages.success(request, f"Organization '{org.name}' ({org.code}){admin_info} created successfully.")

            if admin_user and send_welcome_flag:

                email_status = getattr(org, "_welcome_email_status", None)

                if email_status == "SENT":

                    messages.info(request, f"Login email and password successfully sent to {admin_user.email} via Brevo.")

                elif email_status == "FAILED":

                    messages.warning(

                        request,

                        f"Administrator account created, but welcome email could not be sent: {getattr(org, '_welcome_email_error', 'mail server error')}",

                    )

            elif admin_user and not send_welcome_flag:

                messages.info(request, f"Administrator account '{admin_user.email}' created (welcome email was skipped per checkbox).")

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = OrganizationAdminForm()

    return render(request, "pages/dashboards/superadmin/org_form.html", {"form": form, "is_edit": False})





@login_required

@super_admin_required

def org_edit_view(request, org_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    org = get_object_or_404(Organization.objects.select_related("admin_user"), pk=org_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org or not request.user.is_superuser:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Organization Administrators cannot edit organization details. Only platform super administrators can modify legal entities.</div>",

            status=403,

        )



    if request.method == "POST":

        form = OrganizationAdminForm(request.POST, instance=org)

        if form.is_valid():

            org = form.save()

            admin_email = form.cleaned_data.get("admin_email")

            admin_password = form.cleaned_data.get("admin_password")

            target_user = None

            password_to_send = None

            admin_user_dropdown = form.cleaned_data.get("admin_user")

            if admin_user_dropdown and org.admin_user != admin_user_dropdown:

                org.admin_user = admin_user_dropdown

                org.save(update_fields=["admin_user"])

                if not admin_user_dropdown.organization_id:

                    admin_user_dropdown.organization = org

                    admin_user_dropdown.save(update_fields=["organization"])


            # Handle dedicated Procurement Manager update (1:1)
            pm_email = (form.cleaned_data.get("proc_mgr_email") or "").strip().lower()
            if pm_email:
                role_pm, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})
                pm_user = User.objects.filter(email__iexact=pm_email).first()
                if not pm_user:
                    pm_user = User.objects.create_user(
                        email=pm_email,
                        username=pm_email,
                        first_name=form.cleaned_data.get("proc_mgr_first_name", ""),
                        last_name=form.cleaned_data.get("proc_mgr_last_name", ""),
                        role=role_pm,
                        organization=org,
                    )
                else:
                    pm_user.organization = org
                    pm_user.role = role_pm
                    if form.cleaned_data.get("proc_mgr_first_name"):
                        pm_user.first_name = form.cleaned_data.get("proc_mgr_first_name")
                    if form.cleaned_data.get("proc_mgr_last_name"):
                        pm_user.last_name = form.cleaned_data.get("proc_mgr_last_name")
                    pm_user.save()
                org.procurement_manager = pm_user
                org.save(update_fields=["procurement_manager"])

            # Handle dedicated Compliance Auditor update (1:1)
            aud_email = (form.cleaned_data.get("auditor_email") or "").strip().lower()
            if aud_email:
                role_aud, _ = Role.objects.get_or_create(code=Role.AUDITOR, defaults={"name": "Compliance Auditor"})
                aud_user = User.objects.filter(email__iexact=aud_email).first()
                if not aud_user:
                    aud_user = User.objects.create_user(
                        email=aud_email,
                        username=aud_email,
                        first_name=form.cleaned_data.get("auditor_first_name", ""),
                        last_name=form.cleaned_data.get("auditor_last_name", ""),
                        role=role_aud,
                        organization=org,
                    )
                else:
                    aud_user.organization = org
                    aud_user.role = role_aud
                    if form.cleaned_data.get("auditor_first_name"):
                        aud_user.first_name = form.cleaned_data.get("auditor_first_name")
                    if form.cleaned_data.get("auditor_last_name"):
                        aud_user.last_name = form.cleaned_data.get("auditor_last_name")
                    aud_user.save()
                org.compliance_auditor = aud_user
                org.save(update_fields=["compliance_auditor"])


            if admin_email and (not org.admin_user or org.admin_user.email != admin_email.strip().lower()):

                norm_email = admin_email.strip().lower()

                role, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})

                user = User.objects.filter(email__iexact=norm_email).first()

                if not user:

                    user = User.objects.create_user(

                        email=norm_email,

                        username=norm_email,

                        first_name=form.cleaned_data.get("admin_first_name", ""),

                        last_name=form.cleaned_data.get("admin_last_name", ""),

                        role=role,

                        organization=org,

                    )

                    user.is_staff = False

                else:

                    existing_org = getattr(user, "effective_organization", None) or user.organization
                    if existing_org and existing_org.id != org.id:
                        messages.error(request, "This user does not belong to this organization.")
                        return redirect("superadmin:organizations")
                    if user.is_superuser and not user.organization_id:
                        messages.error(request, f"The email '{norm_email}' is reserved for the Platform Admin and cannot be used.")
                        return redirect("superadmin:organizations")
                    user.organization = org
                    user.role = role
                    user.is_staff = False
                    if form.cleaned_data.get("admin_first_name"):
                        user.first_name = form.cleaned_data.get("admin_first_name")
                    if form.cleaned_data.get("admin_last_name"):
                        user.last_name = form.cleaned_data.get("admin_last_name")
                if admin_password and admin_password.strip():

                    password_to_send = admin_password.strip()

                    user.set_password(password_to_send)

                    user.must_change_password = True

                user.save()

                org.admin_user = user

                org.save(update_fields=["admin_user"])

                target_user = user

            elif org.admin_user:

                admin_first_name = form.cleaned_data.get("admin_first_name", "")

                admin_last_name = form.cleaned_data.get("admin_last_name", "")

                role, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})

                org.admin_user.role = role

                org.admin_user.organization = org

                org.admin_user.is_staff = False

                org.admin_user.is_active = True

                user_updated = True

                if admin_first_name and org.admin_user.first_name != admin_first_name:

                    org.admin_user.first_name = admin_first_name

                if admin_last_name and org.admin_user.last_name != admin_last_name:

                    org.admin_user.last_name = admin_last_name

                if admin_password and admin_password.strip():

                    password_to_send = admin_password.strip()

                    org.admin_user.set_password(password_to_send)

                    org.admin_user.must_change_password = True

                    target_user = org.admin_user

                if user_updated:

                    org.admin_user.save()



            send_welcome_flag = _should_send_welcome_email(

                request,

                default=bool(admin_password and admin_password.strip()) or form.cleaned_data.get("send_welcome_email", False),

            )

            if send_welcome_flag:

                if not target_user and org.admin_user:

                    target_user = org.admin_user

                if not password_to_send and target_user:

                    password_to_send = generate_secure_password()

                    target_user.set_password(password_to_send)

                    target_user.must_change_password = True

                    target_user.save(update_fields=["password", "must_change_password"])



                if target_user and password_to_send:

                    email_status, email_error = send_user_welcome_email(

                        user=target_user,

                        temporary_password=password_to_send,

                        request=request,

                    )

                    if email_status == "SENT":

                        messages.info(request, f"Login email and password successfully sent to {target_user.email} via Brevo.")

                    elif email_status == "QUEUED":

                        messages.info(request, f"Credentials email queued for delivery to {target_user.email}.")

                    else:

                        messages.warning(request, f"Credentials updated, but email could not be delivered: {email_error}")



            messages.success(request, f"Organization '{org.name}' updated successfully.")

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = OrganizationAdminForm(instance=org)

    return render(request, "pages/dashboards/superadmin/org_form.html", {"form": form, "is_edit": True, "org": org})





@login_required

@super_admin_required

def org_detail_view(request, org_id):

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and scoped_org.id != org_id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot view other organizations.</div>",

            status=403,

        )

    org = get_object_or_404(

        Organization.objects.select_related("admin_user").prefetch_related("departments", "departments__cost_centers"),

        pk=org_id,

    )

    departments_count = org.departments.count()

    cost_centers_count = sum(dept.cost_centers.count() for dept in org.departments.all())

    users_count = org.org_users.count()

    vendors_count = org.vendors.count()



    context = {

        "org": org,

        "departments_count": departments_count,

        "cost_centers_count": cost_centers_count,

        "users_count": users_count,

        "vendors_count": vendors_count,

        "departments": org.departments.all()[:10],

        "is_global_superadmin": bool(not scoped_org),

    }

    return render(request, "pages/dashboards/superadmin/org_detail_modal.html", context)





@login_required

@super_admin_required

def org_dashboard_view(request, org_id):

    """

    Dedicated Organization Details Dashboard for Super Admin.

    Provides complete, organization-scoped operational visibility into:

    - Organization master data and assigned administrator

    - Users, roles, and account status (with search, filter, pagination)

    - Departments and cost centers hierarchy

    - Purchase requisitions & approval workflow status

    - Approval activity & decision monitoring

    - Sourcing events & RFQs

    - Vendors, KYC status, and invitations

    - Purchase orders & goods receipts

    - Budgets, spend ledgers, invoices & match exceptions

    - Scoped immutable audit logs

    """

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and scoped_org.id != org_id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot view other organizations.</div>",

            status=403,

        )



    org = get_object_or_404(

        Organization.objects.select_related("admin_user"),

        pk=org_id,

    )



    from decimal import Decimal

    from django.db.models import Sum

    from apps.approvals.models import ApprovalAction
    from apps.budgets.models import Budget
    from apps.contracts.models import Contract
    from apps.invoices.models import MatchException, SupplierInvoice
    from apps.orders.models import PurchaseOrder
    from apps.receipts.models import GoodsReceipt
    from apps.requisitions.models import PurchaseRequisition
    from apps.sourcing.models import SourcingEvent
    from apps.vendors.models import Vendor



    # 1. SCOPED USERS & ROLES

    all_org_users_qs = User.objects.filter(

        Q(organization=org) | Q(department__organization=org)

    ).select_related("role", "department", "cost_center").distinct().order_by("-date_joined")



    total_users_count = all_org_users_qs.count()

    active_users_count = all_org_users_qs.filter(is_active=True).count()

    inactive_users_count = all_org_users_qs.filter(is_active=False).count()



    # User Filters & Search

    q_user = request.GET.get("q_user", "").strip()

    role_filter = request.GET.get("role", "").strip()

    dept_filter = request.GET.get("dept", "").strip()

    status_filter = request.GET.get("status", "").strip()



    filtered_users_qs = all_org_users_qs

    if q_user:

        filtered_users_qs = filtered_users_qs.filter(

            Q(email__icontains=q_user)

            | Q(first_name__icontains=q_user)

            | Q(last_name__icontains=q_user)

            | Q(department__name__icontains=q_user)

            | Q(cost_center__code__icontains=q_user)

            | Q(role__name__icontains=q_user)

        )

    if role_filter:

        filtered_users_qs = filtered_users_qs.filter(role__code=role_filter)

    if dept_filter:

        filtered_users_qs = filtered_users_qs.filter(department_id=dept_filter)

    if status_filter == "active":

        filtered_users_qs = filtered_users_qs.filter(is_active=True)

    elif status_filter == "inactive":

        filtered_users_qs = filtered_users_qs.filter(is_active=False)



    users_page_number = request.GET.get("users_page", 1)

    users_paginator = Paginator(filtered_users_qs, 10)

    users_page_obj = users_paginator.get_page(users_page_number)



    # 2. SCOPED DEPARTMENTS & COST CENTERS

    departments_qs = Department.objects.filter(organization=org).prefetch_related(

        "cost_centers", "cost_centers__manager", "users"

    ).order_by("code")

    departments_count = departments_qs.count()



    cost_centers_qs = CostCenter.objects.filter(department__organization=org).select_related(

        "department", "manager"

    ).order_by("code")

    cost_centers_count = cost_centers_qs.count()



    # 3. SCOPED PURCHASE REQUISITIONS

    prs_qs = PurchaseRequisition.objects.filter(department__organization=org).select_related(

        "requester", "department", "cost_center"

    ).order_by("-created_at")

    total_prs_count = prs_qs.count()

    pending_prs_count = prs_qs.filter(

        status__in=[

            PurchaseRequisition.STATUS_SUBMITTED,

            PurchaseRequisition.STATUS_MANAGER_REVIEW,

            PurchaseRequisition.STATUS_BUDGET_REVIEW,

        ]

    ).count()

    approved_prs_count = prs_qs.filter(status=PurchaseRequisition.STATUS_APPROVED).count()

    rejected_prs_count = prs_qs.filter(status=PurchaseRequisition.STATUS_REJECTED).count()

    draft_prs_count = prs_qs.filter(status=PurchaseRequisition.STATUS_DRAFT).count()



    # 4. SCOPED APPROVAL ACTIONS

    org_pr_ids = list(prs_qs.values_list("id", flat=True))

    approval_actions_qs = ApprovalAction.objects.filter(

        Q(target_object_id__in=org_pr_ids) | Q(actor__in=all_org_users_qs)

    ).select_related("actor", "policy_step").order_by("-created_at")[:50]



    # 5. SCOPED SOURCING EVENTS (RFQs)

    sourcing_events_qs = SourcingEvent.objects.filter(

        requisition__department__organization=org

    ).select_related("requisition", "requisition__department").prefetch_related("invitations", "bids").order_by("-created_at")

    total_rfqs_count = sourcing_events_qs.count()

    active_rfqs_count = sourcing_events_qs.filter(

        status__in=[SourcingEvent.STATUS_PUBLISHED, SourcingEvent.STATUS_BID_WINDOW]

    ).count()

    awarded_rfqs_count = sourcing_events_qs.filter(status=SourcingEvent.STATUS_AWARDED).count()



    # 6. SCOPED VENDORS

    vendors_qs = Vendor.objects.filter(organization=org).select_related("category").order_by("legal_name")

    total_vendors_count = vendors_qs.count()

    active_vendors_count = vendors_qs.filter(status=Vendor.STATUS_ACTIVE).count()

    kyc_review_vendors_count = vendors_qs.filter(status__in=[Vendor.STATUS_SUBMITTED, Vendor.STATUS_KYC_REVIEW]).count()



    # 7. SCOPED PURCHASE ORDERS & RECEIPTS

    pos_qs = PurchaseOrder.objects.filter(cost_center__department__organization=org).select_related(

        "vendor", "cost_center", "requisition"

    ).order_by("-created_at")

    total_pos_count = pos_qs.count()

    open_pos_count = pos_qs.filter(

        status__in=[PurchaseOrder.STATUS_ISSUED, PurchaseOrder.STATUS_ACKNOWLEDGED, PurchaseOrder.STATUS_PARTIAL_RECEIPT]

    ).count()

    completed_pos_count = pos_qs.filter(status=PurchaseOrder.STATUS_COMPLETED).count()



    receipts_qs = GoodsReceipt.objects.filter(po__cost_center__department__organization=org).select_related(

        "po", "received_by"

    ).order_by("-received_date")

    total_receipts_count = receipts_qs.count()



    # 8. SCOPED BUDGETS & FINANCE

    budgets_qs = Budget.objects.filter(cost_center__department__organization=org).select_related(

        "cost_center", "fiscal_period"

    ).order_by("cost_center__code")

    budget_agg = budgets_qs.aggregate(

        allocated=Sum("allocated_amount"),

        reserved=Sum("reserved_amount"),

        committed=Sum("committed_amount"),

        actual=Sum("actual_amount"),

    )

    allocated_budget = budget_agg["allocated"] or Decimal("0.00")

    reserved_budget = budget_agg["reserved"] or Decimal("0.00")

    committed_budget = budget_agg["committed"] or Decimal("0.00")

    actual_budget = budget_agg["actual"] or Decimal("0.00")

    available_budget = allocated_budget - (reserved_budget + committed_budget + actual_budget)

    if available_budget < Decimal("0.00"):

        available_budget = Decimal("0.00")



    invoices_qs = SupplierInvoice.objects.filter(po__cost_center__department__organization=org).select_related(

        "vendor", "po"

    ).order_by("-created_at")

    total_invoices_count = invoices_qs.count()

    total_invoiced_amount = invoices_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")



    exceptions_qs = MatchException.objects.filter(

        invoice__po__cost_center__department__organization=org

    ).select_related("invoice", "invoice__vendor").order_by("-created_at")

    pending_exceptions_count = exceptions_qs.filter(status=MatchException.STATUS_OPEN).count()



    # 9. SCOPED AUDIT LOGS

    audit_logs_qs = AuditLog.objects.filter(

        Q(actor__in=all_org_users_qs) | Q(target_model="Organization", target_object_id=str(org.id))

    ).select_related("actor").order_by("-timestamp")[:50]



    # 10. SCOPED CONTRACTS

    contracts_qs = Contract.objects.filter(

        Q(vendor__organization=org) | Q(po__cost_center__department__organization=org)

    ).select_related("vendor", "contract_owner").order_by("-created_at")

    total_contracts_count = contracts_qs.count()



    # Active tab handling

    active_tab = request.GET.get("tab", "overview")



    # Roles and depts for user filtering

    roles = Role.objects.all().order_by("name")



    context = {

        "org": org,

        "is_global_superadmin": bool(not scoped_org),

        "scoped_org": scoped_org,

        "active_tab": active_tab,

        # Summary metrics

        "total_users_count": total_users_count,

        "active_users_count": active_users_count,

        "inactive_users_count": inactive_users_count,

        "departments_count": departments_count,

        "cost_centers_count": cost_centers_count,

        "total_prs_count": total_prs_count,

        "pending_prs_count": pending_prs_count,

        "approved_prs_count": approved_prs_count,

        "rejected_prs_count": rejected_prs_count,

        "draft_prs_count": draft_prs_count,

        "total_rfqs_count": total_rfqs_count,

        "active_rfqs_count": active_rfqs_count,

        "awarded_rfqs_count": awarded_rfqs_count,

        "total_vendors_count": total_vendors_count,

        "active_vendors_count": active_vendors_count,

        "kyc_review_vendors_count": kyc_review_vendors_count,

        "total_pos_count": total_pos_count,

        "open_pos_count": open_pos_count,

        "completed_pos_count": completed_pos_count,

        "total_receipts_count": total_receipts_count,

        "total_invoices_count": total_invoices_count,

        "total_invoiced_amount": total_invoiced_amount,

        "pending_exceptions_count": pending_exceptions_count,

        "allocated_budget": allocated_budget,

        "reserved_budget": reserved_budget,

        "committed_budget": committed_budget,

        "actual_budget": actual_budget,

        "available_budget": available_budget,

        "total_contracts_count": total_contracts_count,

        # Scoped data collections

        "users_page_obj": users_page_obj,

        "roles": roles,

        "q_user": q_user,

        "role_filter": role_filter,

        "dept_filter": dept_filter,

        "status_filter": status_filter,

        "departments": departments_qs,

        "cost_centers": cost_centers_qs,

        "prs": prs_qs[:30],

        "approval_actions": approval_actions_qs,

        "sourcing_events": sourcing_events_qs[:30],

        "vendors": vendors_qs[:30],

        "purchase_orders": pos_qs[:30],

        "receipts": receipts_qs[:30],

        "budgets": budgets_qs,

        "invoices": invoices_qs[:30],

        "exceptions": exceptions_qs[:30],

        "audit_logs": audit_logs_qs,

        "contracts": contracts_qs[:30],

    }

    return render(request, "pages/dashboards/superadmin/org_dashboard.html", context)





@login_required

@super_admin_required

def org_resend_credentials_view(request, org_id):

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and scoped_org.id != org_id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify other organizations.</div>",

            status=403,

        )

    if request.method != "POST":

        return HttpResponse("<div class='alert alert-danger m-3'>Method not allowed.</div>", status=405)



    org = get_object_or_404(Organization.objects.select_related("admin_user"), pk=org_id)

    if not org.admin_user:

        messages.error(request, f"Organization '{org.name}' has no assigned administrator user.")

        return HttpResponse("<script>window.location.reload();</script>")



    admin_user = org.admin_user

    role, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})

    admin_user.role = role

    admin_user.organization = org

    admin_user.is_staff = False

    admin_user.is_active = True



    new_temp_pwd = generate_secure_password()

    admin_user.set_password(new_temp_pwd)

    admin_user.must_change_password = True

    admin_user.save()



    from apps.audit.services import create_audit_log_service



    create_audit_log_service(

        actor=request.user,

        action=AuditLog.ACTION_UPDATE,

        target_model="User",

        target_object_id=str(admin_user.id),

        previous_state={"credentials_resend": False},

        new_state={"credentials_resend": True, "email": admin_user.email},

        ip_address=request.META.get("REMOTE_ADDR"),

        user_agent=request.META.get("HTTP_USER_AGENT", ""),

    )



    email_status, email_error = send_user_welcome_email(

        user=admin_user,

        temporary_password=new_temp_pwd,

        request=request,

    )



    if email_status == "SENT":

        messages.success(request, f"Login credentials and password successfully sent to {admin_user.email} via Brevo!")

    elif email_status == "QUEUED":

        messages.info(request, f"Credentials email queued for delivery to {admin_user.email}.")

    else:

        messages.warning(request, f"Credentials updated, but Brevo email delivery failed: {email_error}")



    return HttpResponse("<script>window.location.reload();</script>")





@login_required

@super_admin_required

def org_delete_view(request, org_id):

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org is not None or not (request.user.is_superuser or _is_super_admin(request.user)):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Only global platform administrators can delete organizations.</div>",

            status=403,

        )



    org = get_object_or_404(Organization.objects.select_related("admin_user"), pk=org_id)



    # Check if this is the actor's own active organization

    if getattr(request.user, "effective_organization", None) == org:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Cannot delete the active organization your account is assigned to.</div>",

            status=400,

        )



    if request.method == "POST":

        from apps.organization.services import delete_organization_service



        success, message = delete_organization_service(organization=org, actor=request.user, request=request)

        if success:

            messages.success(request, message)

            if request.headers.get("HX-Request"):

                return HttpResponse("<script>window.location.reload();</script>")

            return redirect("superadmin:organizations")

        else:

            messages.error(request, message)

            if request.headers.get("HX-Request"):

                return HttpResponse(f"<div class='alert alert-danger m-3'>{message}</div>")

            return redirect("superadmin:organizations")



    # GET request - return deletion confirmation modal

    departments_count = org.departments.count()

    cost_centers_count = CostCenter.objects.filter(department__organization=org).count()

    users_count = org.org_users.count()



    return render(

        request,

        "pages/dashboards/superadmin/org_delete_modal.html",

        {

            "org": org,

            "departments_count": departments_count,

            "cost_centers_count": cost_centers_count,

            "users_count": users_count,

        },

    )



@login_required

def dept_create_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    if request.method == "POST":

        form = DepartmentAdminForm(request.POST, request=request)

        if form.is_valid():

            dept = form.save(commit=False)

            scoped_org = get_user_scoped_org(request.user)

            if scoped_org:

                dept.organization = scoped_org

            if hasattr(dept, "created_by_id") and not dept.created_by_id:

                dept.created_by = request.user

            dept.save()



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_CREATE,

                target_model="Department",

                target_object_id=str(dept.id),

                previous_state=None,

                new_state={

                    "code": dept.code,

                    "name": dept.name,

                    "organization": dept.organization.code,

                    "description": dept.description,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = DepartmentAdminForm(request=request)

    return render(request, "pages/dashboards/superadmin/dept_form.html", {"form": form, "is_edit": False})





@login_required

def dept_edit_view(request, dept_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    dept = get_object_or_404(Department, pk=dept_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and dept.organization_id != scoped_org.id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify departments of other organizations.</div>",

            status=403,

        )



    if request.method == "POST":

        old_state = {

            "code": dept.code,

            "name": dept.name,

            "organization": dept.organization.code,

            "description": dept.description,

        }

        form = DepartmentAdminForm(request.POST, instance=dept, request=request)

        if form.is_valid():

            dept = form.save()



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_UPDATE,

                target_model="Department",

                target_object_id=str(dept.id),

                previous_state=old_state,

                new_state={

                    "code": dept.code,

                    "name": dept.name,

                    "organization": dept.organization.code,

                    "description": dept.description,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = DepartmentAdminForm(instance=dept, request=request)

    return render(request, "pages/dashboards/superadmin/dept_form.html", {"form": form, "is_edit": True, "dept": dept})





@login_required

def cost_center_create_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    if request.method == "POST":

        form = CostCenterAdminForm(request.POST, request=request)

        if form.is_valid():

            cleaned = form.cleaned_data

            from apps.organization.services import create_cost_center_service



            cost_center = create_cost_center_service(

                department=cleaned["department"],

                code=cleaned["code"],

                name=cleaned["name"],

                manager=cleaned.get("manager"),

            )



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_CREATE,

                target_model="CostCenter",

                target_object_id=str(cost_center.id),

                previous_state=None,

                new_state={

                    "code": cost_center.code,

                    "name": cost_center.name,

                    "department": cost_center.department.code,

                    "manager": cost_center.manager.email if cost_center.manager else None,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = CostCenterAdminForm(request=request)

    return render(

        request,

        "pages/dashboards/superadmin/cost_center_form.html",

        {"form": form, "is_edit": False},

    )





@login_required

def cost_center_edit_view(request, cc_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    cost_center = get_object_or_404(CostCenter, pk=cc_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and cost_center.department.organization_id != scoped_org.id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify cost centers of other organizations.</div>",

            status=403,

        )



    if request.method == "POST":

        old_state = {

            "code": cost_center.code,

            "name": cost_center.name,

            "department": cost_center.department.code,

            "manager": cost_center.manager.email if cost_center.manager else None,

        }

        form = CostCenterAdminForm(request.POST, instance=cost_center, request=request)

        if form.is_valid():

            cost_center = form.save()



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_UPDATE,

                target_model="CostCenter",

                target_object_id=str(cost_center.id),

                previous_state=old_state,

                new_state={

                    "code": cost_center.code,

                    "name": cost_center.name,

                    "department": cost_center.department.code,

                    "manager": cost_center.manager.email if cost_center.manager else None,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = CostCenterAdminForm(instance=cost_center, request=request)

    return render(

        request,

        "pages/dashboards/superadmin/cost_center_form.html",

        {"form": form, "is_edit": True, "cost_center": cost_center},

    )





@login_required

@super_admin_required

def budget_list_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    budgets = Budget.objects.select_related("cost_center", "fiscal_period").all()

    fiscal_periods = FiscalPeriod.objects.select_related("organization").order_by(

        "-year", "-period_number"

    )

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        budgets = budgets.filter(cost_center__department__organization=scoped_org)

        fiscal_periods = fiscal_periods.filter(organization=scoped_org)

    return render(

        request,

        "pages/dashboards/superadmin/budgets.html",

        {"budgets": budgets, "fiscal_periods": fiscal_periods},

    )





@login_required

@super_admin_required

def fiscal_period_create_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    if request.method == "POST":

        form = FiscalPeriodAdminForm(request.POST, request=request)

        if form.is_valid():

            cleaned = form.cleaned_data

            from apps.organization.services import create_fiscal_period_service



            period = create_fiscal_period_service(

                organization=cleaned["organization"],

                year=cleaned["year"],

                period_number=cleaned["period_number"],

                name=cleaned["name"].strip(),

                start_date=cleaned["start_date"],

                end_date=cleaned["end_date"],

            )

            if cleaned.get("is_closed"):

                period.is_closed = True

                period.save(update_fields=["is_closed", "updated_at"])



            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_CREATE,

                target_model="FiscalPeriod",

                target_object_id=str(period.id),

                previous_state=None,

                new_state={

                    "name": period.name,

                    "organization": period.organization.code,

                    "year": period.year,

                    "period_number": period.period_number,

                    "start_date": str(period.start_date),

                    "end_date": str(period.end_date),

                    "is_closed": period.is_closed,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = FiscalPeriodAdminForm(request=request)

    return render(

        request,

        "pages/dashboards/superadmin/fiscal_period_form.html",

        {"form": form, "is_edit": False},

    )





@login_required

@super_admin_required

def fiscal_period_edit_view(request, period_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    period = get_object_or_404(FiscalPeriod, pk=period_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and period.organization_id != scoped_org.id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify fiscal periods of other organizations.</div>",

            status=403,

        )



    if request.method == "POST":

        old_state = {

            "name": period.name,

            "year": period.year,

            "period_number": period.period_number,

            "start_date": str(period.start_date),

            "end_date": str(period.end_date),

            "is_closed": period.is_closed,

        }

        form = FiscalPeriodAdminForm(request.POST, instance=period, request=request)

        if form.is_valid():

            period = form.save()

            from apps.audit.services import create_audit_log_service



            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_UPDATE,

                target_model="FiscalPeriod",

                target_object_id=str(period.id),

                previous_state=old_state,

                new_state={

                    "name": period.name,

                    "year": period.year,

                    "period_number": period.period_number,

                    "start_date": str(period.start_date),

                    "end_date": str(period.end_date),

                    "is_closed": period.is_closed,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = FiscalPeriodAdminForm(instance=period, request=request)

    return render(

        request,

        "pages/dashboards/superadmin/fiscal_period_form.html",

        {"form": form, "is_edit": True, "period": period},

    )





@login_required

@super_admin_required

@login_required
@super_admin_required
def policy_list_view(request):
    if not _is_super_admin(request.user):
        return HttpResponse(
            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",
            status=403,
        )

    scoped_org = get_user_scoped_org(request.user)
    base_qs = ApprovalPolicy.objects.select_related(
        "organization", "department", "cost_center", "exception_department", "exception_cost_center", "exception_approver_role"
    ).prefetch_related("steps", "steps__approver_role", "steps__specific_approver")

    if scoped_org:
        base_qs = base_qs.filter(
            Q(organization=scoped_org) | Q(department__organization=scoped_org)
        )

    # Compute KPI metrics across the scoped set before search/filter
    total_policies = base_qs.count()
    active_policies = base_qs.filter(is_active=True, status=ApprovalPolicy.STATUS_ACTIVE).count()
    draft_policies = base_qs.filter(status=ApprovalPolicy.STATUS_DRAFT).count()
    exception_policies = base_qs.filter(has_exception_routing=True).count()
    archived_policies = base_qs.filter(status=ApprovalPolicy.STATUS_ARCHIVED).count()

    # Search & Filters
    q = request.GET.get("q", "").strip()
    selected_module = request.GET.get("module", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_dept = request.GET.get("department", "").strip()

    filtered_qs = base_qs
    if q:
        filtered_qs = filtered_qs.filter(
            Q(name__icontains=q)
            | Q(module__icontains=q)
            | Q(department__name__icontains=q)
            | Q(department__code__icontains=q)
            | Q(cost_center__code__icontains=q)
            | Q(cost_center__name__icontains=q)
        )
    if selected_module:
        filtered_qs = filtered_qs.filter(module=selected_module)
    if selected_status:
        if selected_status == "ACTIVE":
            filtered_qs = filtered_qs.filter(is_active=True, status=ApprovalPolicy.STATUS_ACTIVE)
        elif selected_status == "INACTIVE":
            filtered_qs = filtered_qs.filter(is_active=False)
        elif selected_status == "DRAFT":
            filtered_qs = filtered_qs.filter(status=ApprovalPolicy.STATUS_DRAFT)
        elif selected_status == "ARCHIVED":
            filtered_qs = filtered_qs.filter(status=ApprovalPolicy.STATUS_ARCHIVED)
        elif selected_status == "WITH_EXCEPTIONS":
            filtered_qs = filtered_qs.filter(has_exception_routing=True)
    if selected_dept:
        filtered_qs = filtered_qs.filter(department_id=selected_dept)

    filtered_qs = filtered_qs.order_by("-is_active", "module", "min_amount", "-created_at")

    # Available departments for filter dropdown
    dept_qs = Department.objects.all().order_by("name")
    if scoped_org:
        dept_qs = dept_qs.filter(organization=scoped_org)

    context = {
        "policies": filtered_qs,
        "departments": dept_qs,
        "module_choices": ApprovalPolicy.MODULE_CHOICES,
        "total_policies": total_policies,
        "active_policies": active_policies,
        "draft_policies": draft_policies,
        "exception_policies": exception_policies,
        "archived_policies": archived_policies,
        "q": q,
        "selected_module": selected_module,
        "selected_status": selected_status,
        "selected_dept": selected_dept,
    }
    return render(request, "pages/dashboards/superadmin/policies.html", context)





def _get_scoped_audit_logs(request):

    logs = AuditLog.objects.select_related("actor").all().order_by("-timestamp")

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        dept_ids = [str(x) for x in Department.objects.filter(organization=scoped_org).values_list("id", flat=True)]

        cc_ids = [str(x) for x in CostCenter.objects.filter(department__organization=scoped_org).values_list("id", flat=True)]

        user_ids = [str(x) for x in User.objects.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org)).values_list("id", flat=True)]



        logs = logs.filter(

            Q(actor__organization=scoped_org)

            | Q(actor__department__organization=scoped_org)

            | Q(target_model="Organization", target_object_id=str(scoped_org.id))

            | Q(target_model="Department", target_object_id__in=dept_ids)

            | Q(target_model="CostCenter", target_object_id__in=cc_ids)

            | Q(target_model="User", target_object_id__in=user_ids)

        )

    return logs





@login_required

@super_admin_required

def audit_list_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    logs_list = _get_scoped_audit_logs(request)

    paginator = Paginator(logs_list, 10)  # Show 10 logs per page



    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)



    return render(request, "pages/dashboards/superadmin/audit.html", {"page_obj": page_obj})





@login_required

@super_admin_required

def budget_create_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    if request.method == "POST":

        form = BudgetAdminForm(request.POST, request=request)

        if form.is_valid():

            form.save()

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = BudgetAdminForm(request=request)

    return render(request, "pages/dashboards/superadmin/budget_form.html", {"form": form, "is_edit": False})





@login_required

@super_admin_required

def budget_edit_view(request, budget_id):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )



    budget = get_object_or_404(Budget, pk=budget_id)

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org and budget.cost_center.department.organization_id != scoped_org.id:

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify budgets of other organizations.</div>",

            status=403,

        )



    if request.method == "POST":

        form = BudgetAdminForm(request.POST, instance=budget, request=request)

        if form.is_valid():

            form.save()

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = BudgetAdminForm(instance=budget, request=request)

    return render(request, "pages/dashboards/superadmin/budget_form.html", {"form": form, "is_edit": True, "budget": budget})





@login_required
@super_admin_required
def policy_create_view(request):
    if not _is_super_admin(request.user):
        return HttpResponse(
            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",
            status=403,
        )

    scoped_org = get_user_scoped_org(request.user)

    if request.method == "POST":
        form = PolicyAdminForm(request.POST, request=request)
        if form.is_valid():
            policy = form.save()
            from apps.audit.models import AuditLog
            AuditLog.objects.create(
                actor=request.user,
                action=AuditLog.ACTION_CREATE,
                target_model="ApprovalPolicy",
                target_object_id=str(policy.id),
                new_state={"name": policy.name, "module": policy.module, "status": policy.status},
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return HttpResponse("<script>window.location.reload();</script>")
    else:
        form = PolicyAdminForm(request=request, initial={"is_active": True, "status": ApprovalPolicy.STATUS_ACTIVE})

    # Prepare default initial steps for builder
    dept_role = Role.objects.filter(code=Role.DEPT_APPROVER).first()
    finance_role = Role.objects.filter(code=Role.FINANCE_AP).first()
    initial_steps = []
    if dept_role:
        initial_steps.append({
            "step_number": 1,
            "role_id": str(dept_role.id),
            "role_name": dept_role.name,
            "user_id": "",
            "user_name": "",
            "description": "Department Approver Review",
            "is_mandatory": True,
            "approval_limit": "",
            "step_type": "SEQUENTIAL",
            "rejection_behavior": "STOP_WORKFLOW",
            "escalation_hours": 48,
        })
    if finance_role:
        initial_steps.append({
            "step_number": 2,
            "role_id": str(finance_role.id),
            "role_name": finance_role.name,
            "user_id": "",
            "user_name": "",
            "description": "Finance / AP Verification",
            "is_mandatory": True,
            "approval_limit": "",
            "step_type": "SEQUENTIAL",
            "rejection_behavior": "STOP_WORKFLOW",
            "escalation_hours": 48,
        })

    available_roles = Role.objects.all().order_by("name")
    user_qs = User.objects.filter(is_active=True).order_by("email")
    if scoped_org:
        user_qs = user_qs.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org))

    return render(
        request,
        "pages/dashboards/superadmin/policy_form.html",
        {
            "form": form,
            "is_edit": False,
            "policy": None,
            "steps_json": json.dumps(initial_steps),
            "available_roles": available_roles,
            "available_users": user_qs,
        },
    )


@login_required
@super_admin_required
def policy_edit_view(request, policy_id):
    if not _is_super_admin(request.user):
        return HttpResponse(
            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",
            status=403,
        )

    policy = get_object_or_404(
        ApprovalPolicy.objects.select_related("organization", "department", "cost_center").prefetch_related("steps", "steps__approver_role", "steps__specific_approver"),
        pk=policy_id
    )
    scoped_org = get_user_scoped_org(request.user)
    if scoped_org:
        if policy.organization_id and policy.organization_id != scoped_org.id:
            return HttpResponse(
                "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify policies of other organizations.</div>",
                status=403,
            )
        elif policy.department and policy.department.organization_id != scoped_org.id:
            return HttpResponse(
                "<div class='alert alert-danger m-3'>Permission Denied: You cannot modify policies of other organizations.</div>",
                status=403,
            )

    if request.method == "POST":
        form = PolicyAdminForm(request.POST, instance=policy, request=request)
        if form.is_valid():
            updated = form.save()
            from apps.audit.models import AuditLog
            AuditLog.objects.create(
                actor=request.user,
                action=AuditLog.ACTION_UPDATE,
                target_model="ApprovalPolicy",
                target_object_id=str(updated.id),
                new_state={"name": updated.name, "module": updated.module, "status": updated.status, "version": updated.version},
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return HttpResponse("<script>window.location.reload();</script>")
    else:
        form = PolicyAdminForm(instance=policy, request=request)

    steps_list = []
    for s in policy.steps.all().order_by("step_number"):
        steps_list.append({
            "step_number": s.step_number,
            "role_id": str(s.approver_role_id) if s.approver_role_id else "",
            "role_name": s.approver_role.name if s.approver_role else "",
            "user_id": str(s.specific_approver_id) if s.specific_approver_id else "",
            "user_name": s.specific_approver.email if s.specific_approver else "",
            "description": s.description or "",
            "is_mandatory": bool(s.is_mandatory),
            "approval_limit": str(s.approval_limit) if s.approval_limit is not None else "",
            "step_type": s.step_type or "SEQUENTIAL",
            "rejection_behavior": s.rejection_behavior or "STOP_WORKFLOW",
            "escalation_hours": s.escalation_hours or "",
        })

    available_roles = Role.objects.all().order_by("name")
    user_qs = User.objects.filter(is_active=True).order_by("email")
    if scoped_org:
        user_qs = user_qs.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org))

    return render(
        request,
        "pages/dashboards/superadmin/policy_form.html",
        {
            "form": form,
            "is_edit": True,
            "policy": policy,
            "steps_json": json.dumps(steps_list),
            "available_roles": available_roles,
            "available_users": user_qs,
        },
    )


@login_required
@super_admin_required
def policy_detail_view(request, policy_id):
    if not _is_super_admin(request.user):
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    policy = get_object_or_404(
        ApprovalPolicy.objects.select_related(
            "organization", "department", "cost_center", "exception_department", "exception_cost_center", "exception_approver_role", "exception_specific_approver"
        ).prefetch_related("steps", "steps__approver_role", "steps__specific_approver"),
        pk=policy_id
    )
    scoped_org = get_user_scoped_org(request.user)
    if scoped_org and policy.organization_id and policy.organization_id != scoped_org.id:
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    steps = policy.steps.all().order_by("step_number")
    from apps.audit.models import AuditLog
    audit_history = AuditLog.objects.filter(
        target_model="ApprovalPolicy",
        target_object_id=str(policy.id),
    ).select_related("actor").order_by("-timestamp")[:10]

    return render(
        request,
        "pages/dashboards/superadmin/policy_detail.html",
        {
            "policy": policy,
            "steps": steps,
            "audit_history": audit_history,
        },
    )


@login_required
@super_admin_required
def policy_duplicate_view(request, policy_id):
    if not _is_super_admin(request.user):
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    from apps.approvals.services import duplicate_approval_policy_service
    scoped_org = get_user_scoped_org(request.user)
    policy = get_object_or_404(ApprovalPolicy, pk=policy_id)
    if scoped_org and policy.organization_id and policy.organization_id != scoped_org.id:
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    try:
        new_policy = duplicate_approval_policy_service(policy_id=policy.id, actor=request.user)
        messages.success(request, f"Policy '{new_policy.name}' created as draft clone of '{policy.name}'.")
    except Exception as e:
        messages.error(request, f"Error duplicating policy: {e}")

    return redirect("/superadmin/policies/")


@login_required
@super_admin_required
def policy_toggle_status_view(request, policy_id):
    if not _is_super_admin(request.user):
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    from apps.approvals.services import toggle_policy_status_service
    scoped_org = get_user_scoped_org(request.user)
    policy = get_object_or_404(ApprovalPolicy, pk=policy_id)
    if scoped_org and policy.organization_id and policy.organization_id != scoped_org.id:
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    try:
        toggled = toggle_policy_status_service(policy=policy, actor=request.user)
        status_label = "activated" if toggled.is_active else "deactivated (moved to Draft)"
        messages.success(request, f"Policy '{toggled.name}' {status_label}.")
    except Exception as e:
        messages.error(request, f"Unable to toggle policy status: {e}")

    return redirect("/superadmin/policies/")


@login_required
@super_admin_required
def policy_archive_view(request, policy_id):
    if not _is_super_admin(request.user):
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    from apps.approvals.services import archive_policy_service
    scoped_org = get_user_scoped_org(request.user)
    policy = get_object_or_404(ApprovalPolicy, pk=policy_id)
    if scoped_org and policy.organization_id and policy.organization_id != scoped_org.id:
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)

    try:
        archived = archive_policy_service(policy=policy, actor=request.user)
        messages.success(request, f"Policy '{archived.name}' has been archived.")
    except Exception as e:
        messages.error(request, f"Error archiving policy: {e}")

    return redirect("/superadmin/policies/")





@login_required

@super_admin_required

def audit_export_view(request):

    if not _is_super_admin(request.user):

        return HttpResponse(

            "<div class='alert alert-danger m-3'>Permission Denied: Super Admin access required.</div>",

            status=403,

        )

    format_type = request.GET.get("format", "csv")

    logs = _get_scoped_audit_logs(request)



    if format_type == "csv":

        response = HttpResponse(content_type="text/csv")

        response["Content-Disposition"] = 'attachment; filename="audit_history.csv"'

        writer = csv.writer(response)

        writer.writerow(["Timestamp", "Actor", "Action", "Target Object", "IP Address", "Comments"])

        for log in logs:

            actor = log.actor.email if log.actor else "System"

            writer.writerow(

                [

                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),

                    actor,

                    log.action,

                    log.readable_target,

                    log.ip_address or "-",

                    getattr(log, "comments", "-") or "-",

                ]

            )

        return response



    elif format_type == "xlsx":

        response = HttpResponse(

            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        )

        response["Content-Disposition"] = 'attachment; filename="audit_history.xlsx"'

        wb = openpyxl.Workbook()

        ws = wb.active

        ws.title = "Audit History"

        ws.append(["Timestamp", "Actor", "Action", "Target Object", "IP Address", "Comments"])

        for log in logs:

            actor = log.actor.email if log.actor else "System"

            ws.append(

                [

                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),

                    actor,

                    log.action,

                    log.readable_target,

                    log.ip_address or "-",

                    getattr(log, "comments", "-") or "-",

                ]

            )

        wb.save(response)

        return response



    elif format_type == "pdf":

        try:

            from reportlab.pdfgen import canvas

        except ImportError:

            return HttpResponse(

                "PDF export is unavailable: reportlab is not installed.", status=501

            )

        response = HttpResponse(content_type="application/pdf")

        response["Content-Disposition"] = 'attachment; filename="audit_history.pdf"'

        p = canvas.Canvas(response)

        y = 800

        p.setFont("Helvetica-Bold", 14)

        p.drawString(50, y, "ProcureSphere 360 - Audit History")

        y -= 30

        p.setFont("Helvetica", 10)



        for log in logs[:100]:  # Limit to 100 for simple PDF layout

            if y < 50:

                p.showPage()

                p.setFont("Helvetica", 10)

                y = 800



            actor = log.actor.email if log.actor else "System"

            line = f"{log.timestamp.strftime('%Y-%m-%d %H:%M')} | {actor} | {log.action} | {log.target_model} #{log.target_object_id}"

            p.drawString(50, y, line)

            y -= 15



        p.showPage()

        p.save()

        return response



    return HttpResponse("Invalid format", status=400)





# ── Locations Master Views ──────────────────────────────────────────────────



@login_required

@super_admin_required

def location_list_view(request):

    """

    List and management view for Organization Locations / Operating Campuses.

    """

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        locations = Location.objects.filter(organization=scoped_org).select_related("organization").order_by("name")

    else:

        locations = Location.objects.all().select_related("organization").order_by("organization__name", "name")



    total_locations = locations.count()

    active_locations = locations.filter(is_active=True).count()

    inactive_locations = total_locations - active_locations



    return render(

        request,

        "pages/dashboards/superadmin/locations.html",

        {

            "locations": locations,

            "total_locations": total_locations,

            "active_locations": active_locations,

            "inactive_locations": inactive_locations,

            "scoped_org": scoped_org,

            "is_org_admin": bool(scoped_org),

        },

    )





@login_required

@super_admin_required

def location_create_view(request):

    scoped_org = get_user_scoped_org(request.user)

    if request.method == "POST":

        form = LocationAdminForm(request.POST, request=request)

        if form.is_valid():

            loc = form.save(commit=False)

            if scoped_org:

                loc.organization = scoped_org

            loc.created_by = request.user

            loc.save()



            from apps.audit.services import create_audit_log_service

            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_CREATE,

                target_model="Location",

                target_object_id=str(loc.id),

                previous_state=None,

                new_state={

                    "code": loc.code,

                    "name": loc.name,

                    "city": loc.city,

                    "organization": loc.organization.code,

                    "is_active": loc.is_active,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            messages.success(request, f"Location '{loc.name}' ({loc.code}) created successfully.")

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = LocationAdminForm(request=request)

    return render(request, "pages/dashboards/superadmin/location_form.html", {"form": form, "is_edit": False})





@login_required

@super_admin_required

def location_edit_view(request, location_id):

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        loc = get_object_or_404(Location, pk=location_id, organization=scoped_org)

    else:

        loc = get_object_or_404(Location, pk=location_id)



    if request.method == "POST":

        form = LocationAdminForm(request.POST, instance=loc, request=request)

        if form.is_valid():

            prev_state = {

                "name": loc.name,

                "code": loc.code,

                "city": loc.city,

                "country": loc.country,

                "is_active": loc.is_active,

            }

            updated_loc = form.save()



            from apps.audit.services import create_audit_log_service

            create_audit_log_service(

                actor=request.user,

                action=AuditLog.ACTION_UPDATE,

                target_model="Location",

                target_object_id=str(updated_loc.id),

                previous_state=prev_state,

                new_state={

                    "name": updated_loc.name,

                    "code": updated_loc.code,

                    "city": updated_loc.city,

                    "country": updated_loc.country,

                    "is_active": updated_loc.is_active,

                },

                ip_address=request.META.get("REMOTE_ADDR"),

                user_agent=request.META.get("HTTP_USER_AGENT", ""),

            )



            messages.success(request, f"Location '{updated_loc.name}' updated successfully.")

            return HttpResponse("<script>window.location.reload();</script>")

    else:

        form = LocationAdminForm(instance=loc, request=request)

    return render(request, "pages/dashboards/superadmin/location_form.html", {"form": form, "is_edit": True})





@login_required

@super_admin_required

def location_delete_view(request, location_id):

    scoped_org = get_user_scoped_org(request.user)

    if scoped_org:

        loc = get_object_or_404(Location, pk=location_id, organization=scoped_org)

    else:

        loc = get_object_or_404(Location, pk=location_id)



    if request.method == "POST":

        loc_name = loc.name

        loc_code = loc.code

        loc_id_str = str(loc.id)



        from apps.audit.services import create_audit_log_service

        create_audit_log_service(

            actor=request.user,

            action=AuditLog.ACTION_DELETE,

            target_model="Location",

            target_object_id=loc_id_str,

            previous_state={"name": loc_name, "code": loc_code, "organization": loc.organization.code},

            new_state=None,

            ip_address=request.META.get("REMOTE_ADDR"),

            user_agent=request.META.get("HTTP_USER_AGENT", ""),

        )

        loc.delete()

        messages.success(request, f"Location '{loc_name}' ({loc_code}) has been deleted.")

    return redirect(request.META.get("HTTP_REFERER", "/superadmin/locations/"))



@login_required
def user_toggle_status_view(request, user_id):
    if not _is_super_admin(request.user):
        return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied.</div>", status=403)
    user = get_object_or_404(User, pk=user_id)
    scoped_org = get_user_scoped_org(request.user)
    if scoped_org:
        user_org_id = user.organization_id or (user.department.organization_id if user.department else None)
        if user_org_id != scoped_org.id:
            return HttpResponse("<div class='alert alert-danger m-3'>Permission Denied: User belongs to another organization.</div>", status=403)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    status_str = "Active" if user.is_active else "Disabled"
    messages.success(request, f"User '{user.email}' is now {status_str}.")
    response = HttpResponse("<script>window.location.reload();</script>")
    response["HX-Refresh"] = "true"
    return response

from decimal import Decimal, InvalidOperation

from django import forms

from django.contrib.auth import password_validation
from django.db.models import Q

from django.db.models import Q
from django.contrib.auth import password_validation

from django.utils import timezone

from apps.accounts.models import Role, User
from apps.accounts.password_utils import generate_secure_password
from apps.approvals.models import ApprovalPolicy
from apps.budgets.models import Budget
from apps.organization.models import CostCenter, Department, FiscalPeriod, Location, Organization


def _get_form_scoped_org(request):



    if not request or not getattr(request, "user", None) or not request.user.is_authenticated:



        return None



    effective_org = getattr(request.user, "effective_organization", None)



    if effective_org:



        return effective_org



    return None











class UserAdminForm(forms.ModelForm):



    password = forms.CharField(



        label="Password",



        required=False,



        widget=forms.PasswordInput(



            attrs={



                "class": "form-control",



                "placeholder": "Enter password or generate",



                "id": "id_password",



                "autocomplete": "new-password",



            }



        ),



    )







    send_welcome_email = forms.BooleanField(



        label="Send Login Credentials Email",



        required=False,



        initial=True,



        widget=forms.CheckboxInput(



            attrs={



                "class": "form-check-input",



                "id": "id_send_welcome_email",



            }



        ),



        help_text="Send email with login credentials (email & password) to the user via Brevo.",



    )







    class Meta:



        model = User
        fields = ["email", "phone_number", "role", "organization", "department", "cost_center", "is_active"]
        widgets = {



            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "user@example.com"}),



            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone number"}),



            "role": forms.Select(attrs={"class": "form-select", "id": "id_role"}),
            "organization": forms.Select(attrs={"class": "form-select", "id": "id_organization"}),
            "department": forms.Select(attrs={"class": "form-select", "id": "id_department"}),



            "cost_center": forms.Select(attrs={"class": "form-select", "id": "id_cost_center"}),



            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),



        }







    def __init__(self, *args, request=None, **kwargs):



        self.request = request



        super().__init__(*args, **kwargs)



        scoped_org = _get_form_scoped_org(request)







        self.fields["email"].required = True



        scoped_org = _get_form_scoped_org(request)
        if not scoped_org and self.instance and getattr(self.instance, "organization_id", None):
            scoped_org = self.instance.organization

        role_qs = Role.objects.all().order_by("name")
        if scoped_org:
            # Exclude roles already assigned in this organization, EXCEPT Role.REQUESTER which is unlimited
            assigned_user_qs = User.objects.filter(
                Q(organization=scoped_org) | Q(department__organization=scoped_org),
                role__isnull=False,
            )
            if self.instance and self.instance.pk and not getattr(self.instance, "_state", None).adding:
                assigned_user_qs = assigned_user_qs.exclude(pk=self.instance.pk)

            assigned_role_ids = set(assigned_user_qs.values_list("role_id", flat=True))
            requester_role = Role.objects.filter(code=Role.REQUESTER).first()
            if requester_role and requester_role.id in assigned_role_ids:
                assigned_role_ids.remove(requester_role.id)

            if assigned_role_ids:
                role_qs = role_qs.exclude(id__in=assigned_role_ids)

        self.fields["role"].queryset = role_qs
        self.fields["role"].empty_label = "-- Select Role --"

        from apps.organization.models import Organization
        if scoped_org:
            self.fields["organization"].queryset = Organization.objects.filter(id=scoped_org.id)
            self.fields["organization"].initial = scoped_org
            self.fields["organization"].widget = forms.HiddenInput()
            self.fields["organization"].required = False
        else:
            self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")
            self.fields["organization"].empty_label = "-- Select Organization --"
            self.fields["organization"].required = False

        dept_qs = Department.objects.select_related("organization").all().order_by("name")



        cc_qs = CostCenter.objects.select_related("department").all().order_by("name")



        if scoped_org:



            dept_qs = dept_qs.filter(organization=scoped_org)



            cc_qs = cc_qs.filter(department__organization=scoped_org)







        self.fields["department"].queryset = dept_qs
        if not self.instance.pk or getattr(self.instance, "_state", None) and self.instance._state.adding:
            self.fields["is_active"].initial = True
            self.initial["is_active"] = True



        self.fields["department"].empty_label = "-- Select Department (Optional) --"



        self.fields["department"].required = False







        self.fields["cost_center"].queryset = cc_qs



        self.fields["cost_center"].empty_label = "-- Select Cost Center --"



        self.fields["cost_center"].required = False







        # In unbound GET edit mode, filter cost centers to the user's department for clean UI rendering.



        # On bound POST submission, keep all cost centers in queryset so clean() can catch cross-department



        # and duplicate assignments with descriptive domain error messages.



        if not self.is_bound and self.instance and self.instance.pk and self.instance.department_id:



            edit_cc_qs = CostCenter.objects.filter(department_id=self.instance.department_id)



            if scoped_org:



                edit_cc_qs = edit_cc_qs.filter(department__organization=scoped_org)



            self.fields["cost_center"].queryset = edit_cc_qs.order_by("name")







        if not self.instance.pk or getattr(self.instance, "_state", None) and self.instance._state.adding:



            self.fields["is_active"].initial = True
            self.initial["is_active"] = True



            self.fields["send_welcome_email"].initial = True
            self.initial["send_welcome_email"] = True



            self.fields["password"].help_text = (



                "Must contain at least 12 characters, including uppercase, lowercase, numbers, and special characters."



            )



        else:



            self.fields["send_welcome_email"].initial = True
            self.initial["send_welcome_email"] = True



            self.fields["password"].help_text = "Leave blank to keep existing password."







    def clean_email(self):



        email = self.cleaned_data.get("email", "").strip().lower()



        if not email:



            raise forms.ValidationError("Email address is required.")



        qs = User.objects.filter(email__iexact=email)



        if self.instance and self.instance.pk and not getattr(self.instance, "_state", None).adding:



            qs = qs.exclude(pk=self.instance.pk)



        if qs.exists():



            raise forms.ValidationError("This user does not belong to this organization.")



        return email







    def clean_password(self):



        password = self.cleaned_data.get("password", "").strip()



        is_creating = not self.instance.pk or (



            getattr(self.instance, "_state", None) and self.instance._state.adding



        )



        if is_creating:



            if not password:



                # If password was omitted or empty, automatically generate a secure random password



                password = generate_secure_password()



                return password







            # Validate password strength with Django's password validators



            user_temp = User(



                email=self.cleaned_data.get("email") or self.data.get("email", ""),



                username=self.cleaned_data.get("email") or self.data.get("email", ""),



            )



            password_validation.validate_password(password, user=user_temp)



            return password



        else:



            # Edit mode: optional



            if password:



                password_validation.validate_password(password, user=self.instance)



            return password







    def clean(self):



        cleaned_data = super().clean()

        role = cleaned_data.get("role")

        # Enforce single user per role in organization, EXCEPT Role.REQUESTER which is unlimited
        if role and role.code != Role.REQUESTER:
            clean_scoped_org = _get_form_scoped_org(self.request) or (
                self.instance.organization if (self.instance and getattr(self.instance, "organization_id", None)) else None
            )
            if clean_scoped_org:
                existing_role_user = User.objects.filter(
                    Q(organization=clean_scoped_org) | Q(department__organization=clean_scoped_org),
                    role=role,
                )
                if self.instance and self.instance.pk and not getattr(self.instance, "_state", None).adding:
                    existing_role_user = existing_role_user.exclude(pk=self.instance.pk)
                if existing_role_user.exists():
                    self.add_error(
                        "role",
                        f"The role '{role.name}' is already assigned to {existing_role_user.first().email}. Each organization can have only one user per role (Requesters are unlimited).",
                    )



        department = cleaned_data.get("department")



        cost_center = cleaned_data.get("cost_center")
        role_code = getattr(role, "code", "") if role else ""

        # 1:1 Dedicated Role Enforcement (Procurement Manager and Auditor)
        target_org = cleaned_data.get("organization") or (department.organization if department else None)
        if not target_org and self.instance and self.instance.pk:
            target_org = getattr(self.instance, "effective_organization", None)

        if role_code in [Role.PROC_MGR, Role.AUDITOR]:
            if not target_org:
                self.add_error("organization", f"An Organization is required for dedicated role '{role.name}'.")
            else:
                if role_code == Role.PROC_MGR:
                    existing_pm = target_org.dedicated_proc_manager
                    if existing_pm and (not self.instance or self.instance.pk != existing_pm.pk):
                        self.add_error("role", f"Organization '{target_org.name}' already has a dedicated Procurement Manager ({existing_pm.email}). Exactly one dedicated Procurement Manager is permitted per organization (1:1).")
                elif role_code == Role.AUDITOR:
                    existing_aud = target_org.dedicated_auditor
                    if existing_aud and (not self.instance or self.instance.pk != existing_aud.pk):
                        self.add_error("role", f"Organization '{target_org.name}' already has a dedicated Compliance Auditor ({existing_aud.email}). Exactly one dedicated Compliance Auditor is permitted per organization (1:1).")







        is_requester = role and getattr(role, "code", "") == Role.REQUESTER







        if is_requester:



            if not department:



                self.add_error("department", "Department is required for Requester accounts.")



            if not cost_center:



                if department and CostCenter.objects.filter(department=department).exists():



                    self.add_error("cost_center", "Cost Center is mandatory for Requester accounts.")



            elif department and cost_center.department_id != department.id:



                self.add_error(



                    "cost_center",



                    f"Cost Center '{cost_center.code}' does not belong to the selected Department '{department.name}'.",



                )



            elif cost_center:



                # Enforce one designated Requester per Cost Center



                existing_req = User.objects.filter(



                    cost_center=cost_center,



                    role__code=Role.REQUESTER,



                    is_active=True,



                )



                if (



                    self.instance



                    and self.instance.pk



                    and not getattr(self.instance, "_state", None).adding



                ):



                    existing_req = existing_req.exclude(pk=self.instance.pk)



                if existing_req.exists():



                    self.add_error(



                        "cost_center",



                        f"Cost Center '{cost_center.code}' already has a designated Requester ({existing_req.first().email}). Each Cost Center can have only one designated Requester.",



                    )



        else:
            # All non-requester roles belong to the entire organization:
            # strictly clear department and cost center!
            cleaned_data["department"] = None
            cleaned_data["cost_center"] = None







        return cleaned_data







    def save(self, commit=True):



        user = super().save(commit=False)



        if self.cleaned_data.get("email"):



            user.username = self.cleaned_data["email"]



        password = self.cleaned_data.get("password")



        if password:



            user.set_password(password)



        elif not user.password:



            temp_pwd = generate_secure_password()



            user.set_password(temp_pwd)



        scoped_org = _get_form_scoped_org(self.request)



        if scoped_org:



            user.organization = scoped_org
        elif user.department and not user.organization_id:
            user.organization = user.department.organization
        elif user.cost_center and user.cost_center.department and not user.organization_id:
            user.organization = user.cost_center.department.organization
        if commit:



            user.save()



        return user











class OrganizationAdminForm(forms.ModelForm):
    # 1. Organization Administrator
    admin_email = forms.EmailField(



        label="Admin Email",



        required=False,



        widget=forms.EmailInput(



            attrs={



                "class": "form-control",



                "id": "id_admin_email",



                "placeholder": "admin@organization.com",



                "autocomplete": "new-admin-email",



                "data-lpignore": "true",



                "data-1p-ignore": "true",



                "data-form-type": "other",



            }



        ),



        help_text="Primary administrator user email for this organization.",



    )



    admin_first_name = forms.CharField(



        label="Admin First Name",



        max_length=150,



        required=False,



        widget=forms.TextInput(



            attrs={



                "class": "form-control",



                "id": "id_admin_first_name",



                "placeholder": "First name",



                "autocomplete": "off",



            }



        ),



    )



    admin_last_name = forms.CharField(



        label="Admin Last Name",



        max_length=150,



        required=False,



        widget=forms.TextInput(



            attrs={



                "class": "form-control",



                "id": "id_admin_last_name",



                "placeholder": "Last name",



                "autocomplete": "off",



            }



        ),



    )



    admin_password = forms.CharField(



        label="Temporary Password",



        required=False,



        widget=forms.PasswordInput(



            attrs={



                "class": "form-control",



                "id": "id_admin_password",



                "placeholder": "Leave blank to auto-generate",



                "autocomplete": "new-password",



                "data-lpignore": "true",



                "data-1p-ignore": "true",



                "data-form-type": "other",



            }



        ),



        help_text="Leave blank to generate a secure temporary password.",



    )



    send_welcome_email = forms.BooleanField(



        label="Send Welcome Email",



        required=False,



        initial=True,



        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_send_welcome_email"}),
        help_text="Send email with login credentials (email & password) to the users via Brevo.",
    )

    # 2. Dedicated Procurement Manager (1:1 per Organization) - Optional
    proc_mgr_email = forms.EmailField(
        label="Procurement Manager Email (Optional)",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "procmgr@organization.com (Optional)"}),
        help_text="Optional: Dedicated Procurement Manager for this organization (1:1). Leave blank to skip.",
    )
    proc_mgr_first_name = forms.CharField(
        label="Manager First Name (Optional)",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name (Optional)"}),
    )
    proc_mgr_last_name = forms.CharField(
        label="Manager Last Name (Optional)",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name (Optional)"}),
    )
    proc_mgr_password = forms.CharField(
        label="Manager Password (Optional)",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Leave blank to auto-generate"}),
        help_text="Leave blank to auto-generate secure password.",
    )

    # 3. Dedicated Compliance Auditor (1:1 per Organization) - Optional
    auditor_email = forms.EmailField(
        label="Compliance Auditor Email (Optional)",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "auditor@organization.com (Optional)"}),
        help_text="Optional: Dedicated Compliance Auditor for this organization (1:1). Leave blank to skip.",
    )
    auditor_first_name = forms.CharField(
        label="Auditor First Name (Optional)",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name (Optional)"}),
    )
    auditor_last_name = forms.CharField(
        label="Auditor Last Name (Optional)",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name (Optional)"}),
    )
    auditor_password = forms.CharField(
        label="Auditor Password (Optional)",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Leave blank to auto-generate"}),
        help_text="Leave blank to auto-generate secure password.",
    )



    import_standard_vendors = forms.BooleanField(



        label="Import Standard Vendor Catalog",



        required=False,



        initial=True,



        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_import_standard_vendors"}),



        help_text="Provision standard active approved suppliers into this new organization for immediate procurement readiness.",



    )







    class Meta:



        model = Organization



        fields = ["code", "name", "tax_identifier", "address", "is_active", "admin_user"]



        widgets = {



            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. HPE-GLOBAL"}),



            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Hewlett Packard Enterprise"}),



            "tax_identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tax ID / EIN"}),



            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Registered address"}),



            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),



            "admin_user": forms.Select(attrs={"class": "form-select"}),



        }







    def __init__(self, *args, **kwargs):



        super().__init__(*args, **kwargs)



        is_create = not self.instance or not self.instance.pk



        self.fields["admin_user"].required = False



        self.fields["admin_user"].empty_label = "-- Select Existing Admin (Optional) --"



        self.fields["admin_user"].queryset = User.objects.filter(



            role__code=Role.SUPER_ADMIN, is_active=True



        ).order_by("email")



        self.fields["admin_email"].required = False



        self.fields["send_welcome_email"].initial = is_create
        self.fields["import_standard_vendors"].initial = is_create

        if is_create:
            self.fields["is_active"].initial = True
            self.initial["is_active"] = True
            self.initial["admin_email"] = ""
            self.initial["admin_password"] = ""
            self.initial["admin_first_name"] = ""
            self.initial["admin_last_name"] = ""

            self.fields["admin_email"].widget.attrs.update({
                "autocomplete": "new-admin-email",
                "readonly": "readonly",
                "onfocus": "this.removeAttribute('readonly');",
                "value": "",
            })
            self.fields["admin_password"].widget.attrs.update({
                "autocomplete": "new-password",
                "readonly": "readonly",
                "onfocus": "this.removeAttribute('readonly');",
                "value": "",
            })
        elif self.instance:
            if self.instance.admin_user:
                self.fields["admin_email"].initial = self.instance.admin_user.email
                self.fields["admin_first_name"].initial = self.instance.admin_user.first_name
                self.fields["admin_last_name"].initial = self.instance.admin_user.last_name
            pm = getattr(self.instance, "procurement_manager", None) or self.instance.dedicated_proc_manager
            if pm:
                self.fields["proc_mgr_email"].initial = pm.email
                self.fields["proc_mgr_first_name"].initial = pm.first_name
                self.fields["proc_mgr_last_name"].initial = pm.last_name
            aud = getattr(self.instance, "compliance_auditor", None) or self.instance.dedicated_auditor
            if aud:
                self.fields["auditor_email"].initial = aud.email
                self.fields["auditor_first_name"].initial = aud.first_name
                self.fields["auditor_last_name"].initial = aud.last_name







    def clean(self):
        cleaned_data = super().clean()
        admin_user = cleaned_data.get("admin_user")
        admin_email = (cleaned_data.get("admin_email") or "").strip()
        proc_mgr_email = (cleaned_data.get("proc_mgr_email") or "").strip()
        auditor_email = (cleaned_data.get("auditor_email") or "").strip()
        is_create = not self.instance or not self.instance.pk

        if is_create and not admin_user and not admin_email:
            self.add_error("admin_email", "Please provide an Admin Email for the organization administrator.")

        email_to_check = admin_email or (admin_user.email if admin_user else "")
        if email_to_check:
            norm_email = email_to_check.strip().lower()
            existing_user = User.objects.filter(email__iexact=norm_email).first()
            if existing_user:
                existing_org = getattr(existing_user, "effective_organization", None) or existing_user.organization
                if existing_org:
                    if is_create or (self.instance and self.instance.pk and str(existing_org.id) != str(self.instance.pk)):
                        self.add_error("admin_email", "This user does not belong to this organization.")
                elif existing_user.is_superuser and not existing_user.organization_id:
                    self.add_error("admin_email", "This user does not belong to this organization.")
                elif is_create:
                    self.add_error("admin_email", "This user does not belong to this organization.")

        if admin_user:
            admin_org = getattr(admin_user, "effective_organization", None) or admin_user.organization
            if admin_org and (is_create or (self.instance and self.instance.pk and str(admin_org.id) != str(self.instance.pk))):
                self.add_error("admin_user", "This user does not belong to this organization.")

        # Ensure distinct emails across provisioned roles
        provided_emails = [e.lower() for e in [admin_email, proc_mgr_email, auditor_email] if e]
        if len(provided_emails) != len(set(provided_emails)):
            self.add_error(None, "Admin, Procurement Manager, and Auditor must each have unique email addresses.")

        return cleaned_data


    def clean_code(self):



        code = self.cleaned_data.get("code", "").strip().upper()



        if not code:



            raise forms.ValidationError("Organization code is required.")



        qs = Organization.objects.filter(code=code)



        if self.instance and self.instance.pk:



            qs = qs.exclude(pk=self.instance.pk)



        if qs.exists():



            raise forms.ValidationError(f"Organization code '{code}' already exists.")



        return code











class DepartmentAdminForm(forms.ModelForm):



    class Meta:



        model = Department



        fields = ["organization", "name", "code", "description"]



        widgets = {



            "organization": forms.Select(attrs={"class": "form-select"}),



            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Human Resources"}),



            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. HR"}),



            "description": forms.Textarea(



                attrs={"class": "form-control", "rows": 3, "placeholder": "Department description (optional)"}



            ),



        }







    def __init__(self, *args, request=None, **kwargs):



        self.request = request



        super().__init__(*args, **kwargs)



        scoped_org = _get_form_scoped_org(request)



        if scoped_org:



            self.fields["organization"].queryset = Organization.objects.filter(id=scoped_org.id)



            self.fields["organization"].initial = scoped_org



            self.fields["organization"].empty_label = None



        else:



            self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")



            self.fields["organization"].empty_label = "-- Select Organization --"







    def clean_organization(self):



        org = self.cleaned_data.get("organization")



        scoped_org = _get_form_scoped_org(self.request)



        if scoped_org and org and org.id != scoped_org.id:



            raise forms.ValidationError("You cannot assign a department to another organization.")



        return org







    def clean_code(self):



        code = self.cleaned_data.get("code", "").strip().upper()



        if not code:



            raise forms.ValidationError("Department code is required.")



        qs = Department.objects.filter(code=code)



        if self.instance and self.instance.pk:



            qs = qs.exclude(pk=self.instance.pk)



        if qs.exists():



            raise forms.ValidationError(f"Department code '{code}' already exists. Code must be unique.")



        return code











class CostCenterAdminForm(forms.ModelForm):



    manager = forms.EmailField(



        required=False,



        widget=forms.EmailInput(



            attrs={



                "class": "form-control",



                "placeholder": "Enter manager email",



                "autocomplete": "off",



            }



        ),



    )







    class Meta:



        model = CostCenter



        fields = ["code", "name", "department"]



        widgets = {



            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CC-IT-101"}),



            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. IT Operations"}),



            "department": forms.Select(attrs={"class": "form-select"}),



        }







    def __init__(self, *args, request=None, **kwargs):



        self.request = request



        super().__init__(*args, **kwargs)



        scoped_org = _get_form_scoped_org(request)



        dept_qs = Department.objects.select_related("organization").all().order_by("name")



        if scoped_org:



            dept_qs = dept_qs.filter(organization=scoped_org)



        self.fields["department"].queryset = dept_qs



        self.fields["department"].empty_label = "-- Select Department --"



        if self.instance.pk and self.instance.manager_id and not self.is_bound:



            self.initial["manager"] = self.instance.manager.email







    def clean_department(self):



        dept = self.cleaned_data.get("department")



        scoped_org = _get_form_scoped_org(self.request)



        if scoped_org and dept and dept.organization_id != scoped_org.id:



            raise forms.ValidationError("You cannot assign a cost center to another organization's department.")



        return dept







    def clean_manager(self):



        raw = (self.cleaned_data.get("manager") or "").strip()



        if not raw:



            return None



        user = User.objects.filter(email__iexact=raw, is_active=True).first()



        if user is None:



            user = User.objects.filter(email__iexact=raw).first()



            if user:



                user.is_active = True



                user.save(update_fields=["is_active"])



            else:



                role, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"})



                dept = self.cleaned_data.get("department") or (self.instance.department if self.instance.pk else None)



                scoped_org = _get_form_scoped_org(self.request) or (dept.organization if dept else None)



                temp_pwd = generate_secure_password()



                user = User.objects.create_user(



                    email=raw.lower(),



                    password=temp_pwd,



                    role=role,



                    organization=scoped_org,



                    department=dept,



                    is_active=True,



                )



                user.must_change_password = True



                user.save(update_fields=["must_change_password"])



                try:



                    from apps.notifications.email_service import send_user_welcome_email



                    send_user_welcome_email(user=user, temporary_password=temp_pwd, request=self.request)



                except Exception:



                    pass



        return user







    def save(self, commit=True):



        instance = super().save(commit=False)



        instance.manager = self.cleaned_data.get("manager")



        if commit:



            instance.save()



            self.save_m2m()



        return instance







    def clean_code(self):



        code = self.cleaned_data.get("code", "").strip().upper()



        if not code:



            raise forms.ValidationError("Cost center code is required.")



        qs = CostCenter.objects.filter(code=code)



        if self.instance and self.instance.pk:



            qs = qs.exclude(pk=self.instance.pk)



        if qs.exists():



            raise forms.ValidationError(f"Cost center code '{code}' already exists. Code must be unique.")



        return code











class BudgetAdminForm(forms.ModelForm):



    class Meta:



        model = Budget



        fields = ["cost_center", "fiscal_period", "allocated_amount", "allow_overspend"]



        widgets = {



            "cost_center": forms.Select(attrs={"class": "form-select"}),



            "fiscal_period": forms.Select(attrs={"class": "form-select"}),



            "allocated_amount": forms.NumberInput(



                attrs={



                    "class": "form-control w-100",



                    "step": "0.01",



                    "min": "0",



                    "max": "999999999999.99",



                    "inputmode": "decimal",



                }



            ),



            "allow_overspend": forms.CheckboxInput(attrs={"class": "form-check-input"}),



        }







    def __init__(self, *args, request=None, **kwargs):



        self.request = request



        super().__init__(*args, **kwargs)



        scoped_org = _get_form_scoped_org(request)



        cc_qs = CostCenter.objects.select_related("department").all().order_by("name")



        fp_qs = FiscalPeriod.objects.all().order_by("-year", "period_number")



        if scoped_org:



            cc_qs = cc_qs.filter(department__organization=scoped_org)



            fp_qs = fp_qs.filter(organization=scoped_org)



        self.fields["cost_center"].queryset = cc_qs



        self.fields["fiscal_period"].queryset = fp_qs



        self.fields["fiscal_period"].label_from_instance = (



            lambda period: f"{period.name} ({period.start_date} to {period.end_date})"



        )



        if fp_qs.exists():



            # Drop the blank "---------" option so the period name and dates are visible.



            self.fields["fiscal_period"].empty_label = None



            if not getattr(self.instance, "pk", None) and not self.is_bound:



                today = timezone.localdate()



                active = fp_qs.filter(



                    is_closed=False, start_date__lte=today, end_date__gte=today



                ).first()



                self.initial["fiscal_period"] = (active or fp_qs.first()).pk



        else:



            self.fields["fiscal_period"].empty_label = "No fiscal period yet — add one first"



        self.fields["allocated_amount"].help_text = (



            "Enter an amount with at most 12 digits before the decimal (max 999,999,999,999.99)."



        )







    def clean_allocated_amount(self):



        amount = self.cleaned_data.get("allocated_amount")



        if amount is None:



            return amount



        try:



            amount = Decimal(amount)



        except (InvalidOperation, TypeError, ValueError):



            raise forms.ValidationError("Enter a valid budget amount.")



        if amount < 0:



            raise forms.ValidationError("Allocated amount cannot be negative.")



        # DecimalField max_digits=14, decimal_places=2 → 12 integer digits.



        if amount.quantize(Decimal("0.01")) >= Decimal("1000000000000"):



            raise forms.ValidationError(



                "Allocated amount is too large. Use at most 12 digits before the decimal."



            )



        return amount.quantize(Decimal("0.01"))











class FiscalPeriodAdminForm(forms.ModelForm):



    class Meta:



        model = FiscalPeriod



        fields = [



            "organization",



            "name",



            "year",



            "period_number",



            "start_date",



            "end_date",



            "is_closed",



        ]



        widgets = {



            "organization": forms.Select(attrs={"class": "form-select"}),



            "name": forms.TextInput(



                attrs={"class": "form-control", "placeholder": "e.g. FY2026-Q1"}



            ),



            "year": forms.NumberInput(



                attrs={"class": "form-control", "placeholder": "2026", "min": "2000"}



            ),



            "period_number": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),



            "start_date": forms.DateInput(



                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"



            ),



            "end_date": forms.DateInput(



                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"



            ),



            "is_closed": forms.CheckboxInput(attrs={"class": "form-check-input"}),



        }







    def __init__(self, *args, request=None, **kwargs):



        self.request = request



        super().__init__(*args, **kwargs)



        self.fields["start_date"].input_formats = ["%Y-%m-%d"]



        self.fields["end_date"].input_formats = ["%Y-%m-%d"]



        current_year = timezone.localdate().year



        self.fields["year"].widget.attrs["min"] = str(current_year)



        scoped_org = _get_form_scoped_org(request)



        if scoped_org:



            self.fields["organization"].queryset = Organization.objects.filter(id=scoped_org.id)



            self.fields["organization"].initial = scoped_org



            self.fields["organization"].empty_label = None



        else:



            self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")



            self.fields["organization"].empty_label = "-- Select Organization --"







    def clean(self):



        cleaned = super().clean()



        start = cleaned.get("start_date")



        end = cleaned.get("end_date")



        if start and end and end < start:



            self.add_error("end_date", "End date must be on or after the start date.")



        current_year = timezone.localdate().year



        year = cleaned.get("year")



        if year is not None and year < current_year:



            self.add_error(



                "year",



                f"Fiscal year cannot be earlier than the current year ({current_year}).",



            )



        if start and start.year < current_year:



            self.add_error(



                "start_date",



                f"Start date cannot be in a year before {current_year}.",



            )



        if end and end.year < current_year:



            self.add_error(



                "end_date",



                f"End date cannot be in a year before {current_year}.",



            )



        org = cleaned.get("organization")



        year = cleaned.get("year")



        period_number = cleaned.get("period_number")



        if org and year and period_number:



            qs = FiscalPeriod.objects.filter(



                organization=org, year=year, period_number=period_number



            )



            if self.instance and self.instance.pk:



                qs = qs.exclude(pk=self.instance.pk)



            if qs.exists():



                self.add_error(



                    "period_number",



                    "This organization already has a fiscal period with that year and period number.",



                )



        return cleaned







    def clean_organization(self):



        org = self.cleaned_data.get("organization")



        scoped_org = _get_form_scoped_org(self.request)



        if scoped_org and org and org.id != scoped_org.id:



            raise forms.ValidationError("You cannot add a fiscal period for another organization.")



        return org











class PolicyAdminForm(forms.ModelForm):
    steps_data = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = ApprovalPolicy
        fields = [
            "name",
            "module",
            "organization",
            "department",
            "cost_center",
            "currency",
            "min_amount",
            "max_amount",
            "status",
            "is_active",
            "description",
            "all_departments",
            "all_cost_centers",
            "has_exception_routing",
            "exception_amount_threshold",
            "exception_department",
            "exception_cost_center",
            "exception_trigger_on_missing_cost_center",
            "exception_trigger_on_budget_exceeded",
            "exception_approver_role",
            "exception_specific_approver",
            "exception_escalation_time_hours",
            "exception_routing_behavior",
            "exception_reason",
            "exception_description",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard PR Approval Policy"}),
            "module": forms.Select(attrs={"class": "form-select", "id": "id_module"}),
            "organization": forms.Select(attrs={"class": "form-select", "id": "id_policy_organization"}),
            "department": forms.Select(attrs={"class": "form-select", "id": "id_policy_department"}),
            "cost_center": forms.Select(attrs={"class": "form-select", "id": "id_policy_cost_center"}),
            "currency": forms.Select(attrs={"class": "form-select", "id": "id_currency"}),
            "min_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
            "max_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Leave blank for unlimited"}),
            "status": forms.Select(attrs={"class": "form-select", "id": "id_policy_status"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_policy_is_active"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Brief description of policy rules"}),
            "all_departments": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_all_departments"}),
            "all_cost_centers": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_all_cost_centers"}),
            "has_exception_routing": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_has_exception_routing"}),
            "exception_amount_threshold": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g. 200000.00"}),
            "exception_department": forms.Select(attrs={"class": "form-select"}),
            "exception_cost_center": forms.Select(attrs={"class": "form-select"}),
            "exception_trigger_on_missing_cost_center": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "exception_trigger_on_budget_exceeded": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "exception_approver_role": forms.Select(attrs={"class": "form-select"}),
            "exception_specific_approver": forms.Select(attrs={"class": "form-select"}),
            "exception_escalation_time_hours": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "exception_routing_behavior": forms.Select(attrs={"class": "form-select"}),
            "exception_reason": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. High-Value Finance Manager Approval"}),
            "exception_description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        scoped_org = _get_form_scoped_org(request)
        if not scoped_org and self.instance and getattr(self.instance, "organization_id", None):
            scoped_org = self.instance.organization

        from apps.organization.models import Organization
        if scoped_org:
            self.fields["organization"].queryset = Organization.objects.filter(id=scoped_org.id)
            self.fields["organization"].initial = scoped_org
            self.fields["organization"].widget = forms.HiddenInput()
            self.fields["organization"].required = False
        else:
            self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")
            self.fields["organization"].empty_label = "-- All Organizations (Global) --"
            self.fields["organization"].required = False

        dept_qs = Department.objects.select_related("organization").all().order_by("name")
        cc_qs = CostCenter.objects.select_related("department").all().order_by("code")
        role_qs = Role.objects.all().order_by("name")
        user_qs = User.objects.filter(is_active=True).order_by("email")

        if scoped_org:
            dept_qs = dept_qs.filter(organization=scoped_org)
            cc_qs = cc_qs.filter(department__organization=scoped_org)
            user_qs = user_qs.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org))

        self.fields["department"].queryset = dept_qs
        self.fields["department"].empty_label = "-- All Departments (Default) --"
        self.fields["department"].required = False

        self.fields["cost_center"].queryset = cc_qs
        self.fields["cost_center"].empty_label = "-- All Cost Centers (Default) --"
        self.fields["cost_center"].required = False

        self.fields["exception_department"].queryset = dept_qs
        self.fields["exception_department"].empty_label = "-- Any Department --"
        self.fields["exception_department"].required = False

        self.fields["exception_cost_center"].queryset = cc_qs
        self.fields["exception_cost_center"].empty_label = "-- Any Cost Center --"
        self.fields["exception_cost_center"].required = False

        self.fields["exception_approver_role"].queryset = role_qs
        self.fields["exception_approver_role"].empty_label = "-- Select Approver Role --"
        self.fields["exception_approver_role"].required = False

        self.fields["exception_specific_approver"].queryset = user_qs
        self.fields["exception_specific_approver"].empty_label = "-- Optional Specific Approver --"
        self.fields["exception_specific_approver"].required = False
        self.fields["exception_routing_behavior"].required = False
        self.fields["exception_routing_behavior"].initial = ApprovalPolicy.EXCEPTION_BEHAVIOR_ADDITIONAL

        if not self.instance.pk or (getattr(self.instance, "_state", None) and self.instance._state.adding):
            self.fields["is_active"].initial = True
            self.initial["is_active"] = True
            self.fields["status"].initial = ApprovalPolicy.STATUS_ACTIVE
            self.initial["status"] = ApprovalPolicy.STATUS_ACTIVE

    def clean(self):
        cleaned_data = super().clean()
        min_amount = cleaned_data.get("min_amount")
        max_amount = cleaned_data.get("max_amount")
        department = cleaned_data.get("department")
        cost_center = cleaned_data.get("cost_center")
        org = cleaned_data.get("organization") or _get_form_scoped_org(self.request)
        module = cleaned_data.get("module")
        is_active = cleaned_data.get("is_active", True)
        status = cleaned_data.get("status", ApprovalPolicy.STATUS_ACTIVE)

        if min_amount is not None and min_amount < Decimal("0.00"):
            self.add_error("min_amount", "Minimum amount cannot be negative.")

        if min_amount is not None and max_amount is not None:
            if min_amount > max_amount:
                self.add_error("min_amount", "Minimum amount cannot be greater than maximum amount.")

        if department and cost_center:
            if cost_center.department_id != department.id:
                self.add_error("cost_center", f"Cost Center '{cost_center.code}' does not belong to Department '{department.name}'.")

        # Conflict & Overlap Detection for Active Policies
        if is_active and status == ApprovalPolicy.STATUS_ACTIVE and module:
            qs = ApprovalPolicy.objects.filter(
                is_active=True,
                status=ApprovalPolicy.STATUS_ACTIVE,
                module=module,
                organization=org,
                department=department,
                cost_center=cost_center,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            for existing in qs:
                e_min = existing.min_amount
                e_max = existing.max_amount
                c_min = min_amount if min_amount is not None else Decimal("0.00")
                c_max = max_amount

                overlap = (e_max is None or c_min <= e_max) and (c_max is None or e_min <= c_max)
                if overlap:
                    e_range = f"{existing.min_amount} - {existing.max_amount or 'Unlimited'}"
                    self.add_error(
                        "min_amount",
                        f"Amount range overlaps with existing active policy '{existing.name}' ({e_range}). "
                        "Conflicting overlapping policies with identical scope are not permitted."
                    )
                    break

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        scoped_org = _get_form_scoped_org(self.request)
        if scoped_org and not instance.organization_id:
            instance.organization = scoped_org

        if commit:
            instance.save()
            self._save_dynamic_steps(instance)
            self._ensure_policy_steps(instance)
        return instance

    def _save_dynamic_steps(self, policy):
        import json
        import logging
        logger = logging.getLogger(__name__)

        raw_steps_data = self.data.get("steps_data")
        if not raw_steps_data:
            return

        try:
            steps_list = json.loads(raw_steps_data)
            if not isinstance(steps_list, list) or len(steps_list) == 0:
                return

            from apps.approvals.models import ApprovalStep
            policy.steps.all().delete()

            for idx, s in enumerate(steps_list, start=1):
                role_id = s.get("role_id")
                if not role_id:
                    continue
                role_obj = Role.objects.filter(id=role_id).first()
                if not role_obj:
                    continue

                user_id = s.get("user_id")
                specific_user = User.objects.filter(id=user_id).first() if user_id else None

                ApprovalStep.objects.create(
                    policy=policy,
                    step_number=idx,
                    approver_role=role_obj,
                    specific_approver=specific_user,
                    description=s.get("description", f"{role_obj.name} Approval"),
                    is_mandatory=bool(s.get("is_mandatory", True)),
                    approval_limit=Decimal(str(s["approval_limit"])) if s.get("approval_limit") else None,
                    step_type=s.get("step_type", "SEQUENTIAL"),
                    rejection_behavior=s.get("rejection_behavior", "STOP_WORKFLOW"),
                    escalation_hours=int(s["escalation_hours"]) if s.get("escalation_hours") else None,
                )
        except Exception as e:
            logger.warning("Error saving dynamic approval steps in PolicyAdminForm: %s", e)

    def _ensure_policy_steps(self, policy):
        if policy.steps.exists():
            return

        from apps.accounts.models import Role
        from apps.approvals.models import ApprovalStep

        dept_role = Role.objects.filter(code=Role.DEPT_APPROVER).first()
        proc_role = Role.objects.filter(code=Role.PROC_MGR).first()
        finance_role = Role.objects.filter(code=Role.FINANCE_AP).first()

        if policy.module == ApprovalPolicy.MODULE_PR:
            if dept_role:
                ApprovalStep.objects.get_or_create(
                    policy=policy,
                    step_number=1,
                    defaults={
                        "approver_role": dept_role,
                        "description": "Department Approver Review",
                    },
                )
            if finance_role:
                ApprovalStep.objects.get_or_create(
                    policy=policy,
                    step_number=2,
                    defaults={
                        "approver_role": finance_role,
                        "description": "Finance / AP Approval",
                    },
                )
        elif policy.module == ApprovalPolicy.MODULE_PO_AMENDMENT and proc_role:
            ApprovalStep.objects.get_or_create(
                policy=policy,
                step_number=1,
                defaults={
                    "approver_role": proc_role,
                    "description": "Procurement Manager Approval",
                },
            )
        elif dept_role:
            ApprovalStep.objects.get_or_create(
                policy=policy,
                step_number=1,
                defaults={
                    "approver_role": dept_role,
                    "description": "Department Approval",
                },
            )







class LocationAdminForm(forms.ModelForm):

    class Meta:

        model = Location

        fields = ["organization", "name", "code", "city", "country", "address", "is_active"]

        widgets = {

            "organization": forms.Select(attrs={"class": "form-select"}),

            "name": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "e.g. Hyderabad Campus / Operations Chennai",

                }

            ),

            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. LOC-HYD"}),

            "city": forms.TextInput(

                attrs={"class": "form-control", "placeholder": "e.g. Hyderabad / Chennai / Bangalore"}

            ),

            "country": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. India"}),

            "address": forms.Textarea(

                attrs={

                    "class": "form-control",

                    "rows": 2,

                    "placeholder": "Physical facility address (optional)",

                }

            ),

            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),

        }



    def __init__(self, *args, request=None, **kwargs):

        self.request = request

        super().__init__(*args, **kwargs)

        scoped_org = _get_form_scoped_org(request)

        if scoped_org:

            self.fields["organization"].queryset = Organization.objects.filter(id=scoped_org.id)

            self.fields["organization"].initial = scoped_org

            self.fields["organization"].empty_label = None

        else:

            self.fields["organization"].queryset = Organization.objects.filter(is_active=True).order_by("name")

            self.fields["organization"].empty_label = "-- Select Organization --"



        if not self.instance.pk:

            self.fields["country"].initial = "India"

            self.fields["is_active"].initial = True



    def clean_code(self):

        code = self.cleaned_data.get("code", "").strip().upper()

        if not code:

            raise forms.ValidationError("Location code is required.")

        org = self.cleaned_data.get("organization") or _get_form_scoped_org(self.request)

        if org:

            qs = Location.objects.filter(organization=org, code=code)

            if self.instance and self.instance.pk:

                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():

                raise forms.ValidationError(f"Location code '{code}' already exists for {org.name}.")

        return code


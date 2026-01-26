"""
context_processor.py

This module is used to register context processor with AGGRESSIVE CACHING
for ultra-fast page loads.
"""

import re

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from base.models import Company, TrackLateComeEarlyOut
from base.urls import urlpatterns
from employee.models import (
    Employee,
    EmployeeGeneralSetting,
    EmployeeWorkInformation,
    ProfileEditFeature,
)
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.methods import get_horilla_model_class

# Cache timeouts (in seconds)
SETTINGS_CACHE_TIMEOUT = 300  # 5 minutes for settings
COMPANY_CACHE_TIMEOUT = 300   # 5 minutes for company list


class AllCompany:
    """
    Dummy class
    """

    class Urls:
        url = "https://ui-avatars.com/api/?name=All+Company&background=random"

    company = "All Company"
    icon = Urls()
    text = "All companies"
    id = None


def get_last_section(path):
    # Remove any trailing slash and split the path
    segments = path.strip("/").split("/")

    # Get the last section (the ID)
    last_section = segments[-1] if segments else None
    return last_section


def _get_cached_companies():
    """
    Get cached company list - single DB query, cached for 5 minutes
    """
    cache_key = "ctx_companies_list"
    companies = cache.get(cache_key)
    
    if companies is None:
        companies = list(
            [company.id, company.company, company.icon.url if company.icon else "", False]
            for company in Company.objects.only('id', 'company', 'icon').all()
        )
        cache.set(cache_key, companies, COMPANY_CACHE_TIMEOUT)
    
    return companies


def get_companies(request):
    """
    This method will return the company list - CACHED
    """
    # Get cached companies (DB query cached)
    companies = [list(c) for c in _get_cached_companies()]  # Deep copy
    
    companies = [
        [
            "all",
            "All Company",
            "https://ui-avatars.com/api/?name=All+Company&background=random",
            False,
        ],
    ] + companies
    
    selected_company = request.session.get("selected_company")
    company_selected = False
    
    if selected_company and selected_company == "all":
        companies[0][3] = True
        company_selected = True
    else:
        for company in companies:
            if str(company[0]) == selected_company:
                company[3] = True
                company_selected = True
    
    return {"all_companies": companies, "company_selected": company_selected}


@login_required
@hx_request_required
@permission_required("base.change_company")
def update_selected_company(request):
    """
    This method is used to update the selected company on the session
    """
    company_id = request.GET.get("company_id")
    user = request.user.employee_get
    user_company = getattr(
        getattr(user, "employee_work_info", None), "company_id", None
    )
    request.session["selected_company"] = company_id
    company = (
        AllCompany()
        if company_id == "all"
        else (
            Company.objects.filter(id=company_id).first()
            if Company.objects.filter(id=company_id).first()
            else AllCompany()
        )
    )
    previous_path = request.GET.get("next", "/")
    # Define the regex pattern for the path
    pattern = r"^/employee/employee-view/\d+/$"
    # Check if the previous path matches the pattern
    if company_id != "all":
        if re.match(pattern, previous_path):
            employee_id = get_last_section(previous_path)
            employee = Employee.objects.filter(id=employee_id).first()
            emp_company = getattr(
                getattr(employee, "employee_work_info", None), "company_id", None
            )
            if emp_company != company:
                text = "Other Company"
                if company_id == user_company:
                    text = "My Company"
                company = {
                    "company": company.company,
                    "icon": company.icon.url,
                    "text": text,
                    "id": company.id,
                }
                messages.error(
                    request, _("Employee is not working in the selected company.")
                )
                request.session["selected_company_instance"] = company
                return HttpResponse(
                    f"""
                    <script>window.location.href = `{reverse("employee-view")}`</script>
                """
                )

    if company_id == "all":
        text = "All companies"
    elif company_id == user_company:
        text = "My Company"
    else:
        text = "Other Company"

    company = {
        "company": company.company,
        "icon": company.icon.url,
        "text": text,
        "id": company.id,
    }
    request.session["selected_company_instance"] = company
    # Invalidate company cache when company selection changes
    cache.delete("ctx_companies_list")
    return HttpResponse("<script>window.location.reload();</script>")


urlpatterns.append(
    path(
        "update-selected-company",
        update_selected_company,
        name="update-selected-company",
    )
)


def _get_all_general_settings():
    """
    Fetch ALL general settings in ONE cached call.
    This replaces 7+ individual DB queries with 1 cached result.
    """
    cache_key = "ctx_all_general_settings"
    cached = cache.get(cache_key)
    
    if cached is not None:
        return cached
    
    result = {
        "offboarding": None,
        "attendance": None,
        "payroll": None,
        "recruitment": None,
        "employee": None,
        "late_tracking": None,
        "profile_edit": None,
        "hq_company": None,
    }
    
    # Offboarding settings
    if apps.is_installed("offboarding"):
        try:
            OffboardingGeneralSetting = get_horilla_model_class(
                app_label="offboarding", model="offboardinggeneralsetting"
            )
            result["offboarding"] = OffboardingGeneralSetting.objects.first()
        except:
            pass
    
    # Attendance settings
    if apps.is_installed("attendance"):
        try:
            AttendanceGeneralSetting = get_horilla_model_class(
                app_label="attendance", model="attendancegeneralsetting"
            )
            result["attendance"] = AttendanceGeneralSetting.objects.first()
        except:
            pass
    
    # Payroll settings
    if apps.is_installed("payroll"):
        try:
            PayrollGeneralSetting = get_horilla_model_class(
                app_label="payroll", model="payrollgeneralsetting"
            )
            result["payroll"] = PayrollGeneralSetting.objects.first()
        except:
            pass
    
    # Recruitment settings
    if apps.is_installed("recruitment"):
        try:
            RecruitmentGeneralSetting = get_horilla_model_class(
                app_label="recruitment", model="recruitmentgeneralsetting"
            )
            result["recruitment"] = RecruitmentGeneralSetting.objects.first()
        except:
            pass
    
    # Employee settings
    try:
        result["employee"] = EmployeeGeneralSetting.objects.first()
    except:
        pass
    
    # Late tracking
    try:
        result["late_tracking"] = TrackLateComeEarlyOut.objects.first()
    except:
        pass
    
    # Profile edit
    try:
        result["profile_edit"] = ProfileEditFeature.objects.first()
    except:
        pass
    
    # HQ Company
    try:
        result["hq_company"] = Company.objects.filter(hq=True).only('id', 'company', 'icon').last()
    except:
        pass
    
    cache.set(cache_key, result, SETTINGS_CACHE_TIMEOUT)
    return result


def white_labelling_company(request):
    """
    CACHED - uses shared settings cache
    """
    white_labelling = getattr(settings, "WHITE_LABELLING", False)
    if white_labelling:
        all_settings = _get_all_general_settings()
        hq = all_settings.get("hq_company")
        try:
            company = (
                request.user.employee_get.get_company()
                if request.user.employee_get.get_company()
                else hq
            )
        except:
            company = hq

        return {
            "white_label_company_name": company.company if company else "Horilla",
            "white_label_company": company,
        }
    else:
        return {
            "white_label_company_name": "Horilla",
            "white_label_company": None,
        }


def resignation_request_enabled(request):
    """
    CACHED - Check if resignation_request enabled in offboarding
    """
    all_settings = _get_all_general_settings()
    first = all_settings.get("offboarding")
    enabled_resignation_request = first.resignation_request if first else False
    return {"enabled_resignation_request": enabled_resignation_request}


def timerunner_enabled(request):
    """
    CACHED - Check if timerunner enabled in attendance
    """
    all_settings = _get_all_general_settings()
    first = all_settings.get("attendance")
    enabled_timerunner = first.time_runner if first else True
    return {"enabled_timerunner": enabled_timerunner}


def intial_notice_period(request):
    """
    CACHED - Get notice period from payroll
    """
    all_settings = _get_all_general_settings()
    first = all_settings.get("payroll")
    initial = first.notice_period if first else 30
    return {"get_initial_notice_period": initial}


def check_candidate_self_tracking(request):
    """
    CACHED - Check if candidate self tracking is enabled
    """
    all_settings = _get_all_general_settings()
    first = all_settings.get("recruitment")
    candidate_self_tracking = first.candidate_self_tracking if first else False
    return {"check_candidate_self_tracking": candidate_self_tracking}


def check_candidate_self_tracking_rating(request):
    """
    CACHED - Check if rating option is enabled
    """
    all_settings = _get_all_general_settings()
    first = all_settings.get("recruitment")
    rating_option = first.show_overall_rating if first else False
    return {"check_candidate_self_tracking_rating": rating_option}


def get_initial_prefix(request):
    """
    CACHED - Get the initial badge prefix
    """
    all_settings = _get_all_general_settings()
    emp_settings = all_settings.get("employee")
    instance_id = None
    prefix = "PEP"
    if emp_settings:
        instance_id = emp_settings.id
        prefix = emp_settings.badge_id_prefix
    return {"get_initial_prefix": prefix, "prefix_instance_id": instance_id}


def biometric_app_exists(request):
    """
    NO DB QUERY - Just checks installed apps (already fast)
    """
    from django.conf import settings
    biometric_app_exists = "biometric" in settings.INSTALLED_APPS
    return {"biometric_app_exists": biometric_app_exists}


def enable_late_come_early_out_tracking(request):
    """
    CACHED - Check late come early out tracking
    """
    all_settings = _get_all_general_settings()
    tracking = all_settings.get("late_tracking")
    enable = tracking.is_enable if tracking else True
    return {"tracking": enable, "late_come_early_out_tracking": enable}


def enable_profile_edit(request):
    """
    CACHED - Check if profile edit is enabled
    """
    from accessibility.accessibility import ACCESSBILITY_FEATURE

    all_settings = _get_all_general_settings()
    profile_edit = all_settings.get("profile_edit")
    enable = False if profile_edit and profile_edit.is_enabled else True
    if enable:
        if not any(item[0] == "profile_edit" for item in ACCESSBILITY_FEATURE):
            ACCESSBILITY_FEATURE.append(("profile_edit", _("Profile Edit Access")))

    return {"profile_edit_enabled": enable}


def invalidate_settings_cache():
    """
    Call this when any general setting is updated to clear the cache.
    Can be connected to post_save signals.
    """
    cache.delete("ctx_all_general_settings")
    cache.delete("ctx_companies_list")

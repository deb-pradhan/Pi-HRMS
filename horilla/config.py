"""
horilla/config.py

Horilla app configurations with OPTIMIZED SIDEBAR CACHING
"""

import importlib
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache timeout for sidebar (in seconds)
SIDEBAR_CACHE_TIMEOUT = 300  # 5 minutes


def get_apps_in_base_dir():
    return settings.SIDEBARS


def import_method(accessibility):
    module_path, method_name = accessibility.rsplit(".", 1)
    module = __import__(module_path, fromlist=[method_name])
    accessibility_method = getattr(module, method_name)
    return accessibility_method


ALL_MENUS = {}


def _build_sidebar(request):
    """
    Build the sidebar menu structure.
    Separated from caching logic for clarity.
    """
    base_dir_apps = get_apps_in_base_dir()
    MENUS = []

    for app in base_dir_apps:
        if apps.is_installed(app):
            try:
                sidebar = importlib.import_module(app + ".sidebar")
            except Exception as e:
                logger.error(e)
                continue

            if sidebar:
                accessibility = None
                if getattr(sidebar, "ACCESSIBILITY", None):
                    accessibility = import_method(sidebar.ACCESSIBILITY)

                if hasattr(sidebar, "MENU") and (
                    not accessibility
                    or accessibility(
                        request,
                        sidebar.MENU,
                        PermWrapper(request.user),
                    )
                ):
                    MENU = {}
                    MENU["menu"] = sidebar.MENU
                    MENU["app"] = app
                    MENU["img_src"] = sidebar.IMG_SRC
                    MENU["submenu"] = []
                    MENUS.append(MENU)
                    
                    for submenu in sidebar.SUBMENUS:
                        accessibility = None
                        if submenu.get("accessibility"):
                            accessibility = import_method(submenu["accessibility"])
                        redirect = submenu["redirect"]
                        redirect = redirect.split("?")
                        submenu["redirect"] = redirect[0]

                        if not accessibility or accessibility(
                            request,
                            submenu,
                            PermWrapper(request.user),
                        ):
                            MENU["submenu"].append(submenu)
    
    return MENUS


def sidebar(request):
    """
    Build sidebar with caching per user.
    Cache key is based on user ID to handle different permissions.
    """
    if request.user.is_anonymous:
        return
    
    user_id = request.user.id
    cache_key = f"sidebar_menu_user_{user_id}"
    
    # Try to get from cache first
    cached_menus = cache.get(cache_key)
    
    if cached_menus is not None:
        request.MENUS = cached_menus
        ALL_MENUS[request.session.session_key] = cached_menus
        return
    
    # Build fresh if not cached
    MENUS = _build_sidebar(request)
    
    # Store in cache
    cache.set(cache_key, MENUS, SIDEBAR_CACHE_TIMEOUT)
    
    # Also store in request/session for immediate use
    request.MENUS = MENUS
    ALL_MENUS[request.session.session_key] = MENUS


def get_MENUS(request):
    """
    Get sidebar menus - with caching optimization.
    """
    if request.user.is_anonymous:
        return {"sidebar": []}
    
    sidebar(request)
    return {"sidebar": ALL_MENUS.get(request.session.session_key, [])}


def invalidate_sidebar_cache(user_id=None):
    """
    Invalidate sidebar cache.
    Call when permissions change or on logout.
    
    Args:
        user_id: Specific user ID to invalidate, or None to invalidate all
    """
    if user_id:
        cache.delete(f"sidebar_menu_user_{user_id}")
    else:
        # Pattern delete not always available, so we rely on timeout
        pass


def load_ldap_settings():
    """
    Fetch LDAP settings dynamically from the database after Django is ready.
    """
    try:
        from django.db import connection

        from horilla_ldap.models import LDAPSettings

        # Ensure DB is ready before querying
        if not connection.introspection.table_names():
            print("⚠️ Database is empty. Using default LDAP settings.")
            return settings.DEFAULT_LDAP_CONFIG

        ldap_config = LDAPSettings.objects.first()
        if ldap_config:
            return {
                "LDAP_SERVER": ldap_config.ldap_server,
                "BIND_DN": ldap_config.bind_dn,
                "BIND_PASSWORD": ldap_config.bind_password,
                "BASE_DN": ldap_config.base_dn,
            }
    except Exception as e:
        print(f"⚠️ Warning: Could not load LDAP settings ({e})")
        return settings.DEFAULT_LDAP_CONFIG  # Return default on error

    return settings.DEFAULT_LDAP_CONFIG  # Fallback in case of an issue

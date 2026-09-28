from rest_framework.permissions import BasePermission
from .views import _get_authenticated_admin, _get_authenticated_vendor

class IsAdminAuthenticated(BasePermission):
    """
    Allows access only to authenticated staff with a valid session version.
    """
    def has_permission(self, request, view):
        admin_user = _get_authenticated_admin(request)
        if not admin_user:
            return False
        request.admin_user = admin_user
        return True


class IsSuperAdmin(BasePermission):
    """
    Allows access only to SuperAdmin accounts.
    """
    def has_permission(self, request, view):
        admin_user = _get_authenticated_admin(request)
        if not admin_user:
            return False
        request.admin_user = admin_user
        return admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com"


class IsXLSXAdmin(BasePermission):
    """
    Allows access to XLSX Admins and SuperAdmins.
    """
    def has_permission(self, request, view):
        admin_user = _get_authenticated_admin(request)
        if not admin_user:
            return False
        request.admin_user = admin_user
        return admin_user.account_type in ["XLSXAdmin", "SuperAdmin"]


class IsVendor(BasePermission):
    """
    Allows access to Vendor accounts.
    """
    def has_permission(self, request, view):
        vendor_user = _get_authenticated_vendor(request)
        if not vendor_user:
            return False
        request.vendor_user = vendor_user
        return True

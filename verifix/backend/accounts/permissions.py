from rest_framework import permissions


class IsAdminRole(permissions.BasePermission):
    """Faqat admin yoki superuser uchun."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin_role)


class IsHRRole(permissions.BasePermission):
    """HR yoki Admin uchun."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_hr_role)


class IsSelfOrHR(permissions.BasePermission):
    """O'z resursini ko'rish yoki HR/Admin."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_hr_role:
            return True
        owner_id = getattr(obj, "user_id", None) or getattr(obj, "id", None)
        return owner_id == request.user.id

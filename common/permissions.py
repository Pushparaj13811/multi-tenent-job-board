"""
Custom permission classes for HireFlow.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsRecruiter(BasePermission):
    """Allow access only to authenticated users with role='recruiter'."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "recruiter"
        )


class IsCandidate(BasePermission):
    """Allow access only to authenticated users with role='candidate'."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "candidate"
        )


class IsCompanyMember(BasePermission):
    """
    Allow access only to members of the company associated with the object.
    Resolves company from obj.company or obj itself (if obj is a Company).
    Tested with real DB objects in Phase 4.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        company = getattr(obj, "company", obj)
        return company.members.filter(user=request.user).exists()


class IsOwnerOrReadOnly(BasePermission):
    """
    Allow read-only access to anyone.
    Write operations only allowed if obj is the request user,
    or obj.applicant is the request user.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        # Check if the object itself is the user, or has an applicant field
        if obj == request.user:
            return True
        return getattr(obj, "applicant", None) == request.user

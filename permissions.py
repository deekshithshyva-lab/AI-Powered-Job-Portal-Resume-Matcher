from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsRecruiter(BasePermission):
    message = "Recruiter role required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_recruiter)


class IsApplicant(BasePermission):
    message = "Applicant role required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_applicant)


class IsRecruiterOrReadOnly(BasePermission):
    """Any authenticated user may read; only recruiters may write."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or request.user.is_recruiter


class IsJobOwnerOrReadOnly(BasePermission):
    """Only the recruiter who posted a job may modify or delete it."""

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.posted_by_id == request.user.id

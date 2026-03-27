from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from functools import wraps


def get_user_role(user):
    """사용자의 역할을 반환. Django superuser는 항상 admin. 프로필이 없으면 'se' 반환."""
    if user.is_superuser:
        return 'admin'
    try:
        return user.profile.role
    except AttributeError:
        return 'se'


def has_role(user, *roles):
    """Admin은 항상 True. 나머지는 roles 목록에 포함 여부 확인."""
    role = get_user_role(user)
    return role in ('admin', 'manager') or role in roles


class RoleRequiredMixin(LoginRequiredMixin):
    """CBV용 역할 제한 믹스인. allowed_roles가 비어 있으면 Admin 전용."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not has_role(request.user, *self.allowed_roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def role_required(*roles):
    """FBV용 데코레이터. Admin은 항상 통과. roles가 비어 있으면 Admin 전용."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator

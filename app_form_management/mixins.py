from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class FormManagementAccessMixin(UnifiedAccessMixin):
    identity_required = [IdentityConfig.INTERNAL_STAFF]
    enforce_dept_isolation = False

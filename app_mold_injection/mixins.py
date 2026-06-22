from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class InjectionTaskAccessMixin(UnifiedAccessMixin):
    """注塑任务 — 仅注塑操作员 + 技术核心 + 管理员"""
    user_link_fields = ['operator']
    identity_required = IdentityConfig.INJECTION_TEAM

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return None
        user = self.request.user
        if user.user_type in [IdentityConfig.R_INJECTION_OP]:
            model = qs.model
            model_fields = [f.name for f in model._meta.get_fields()]
            if 'operator' in model_fields:
                from django.db.models import Q
                qs = qs.filter(
                    Q(operator=user) | Q(operator__isnull=True)
                )
        return qs


class MoldManageAccessMixin(UnifiedAccessMixin):
    """模具台账管理 — 仅技术核心 + 管理员"""
    identity_required = IdentityConfig.TECH_CORE
    enforce_dept_isolation = False

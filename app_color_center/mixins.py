from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class ColorCenterAccessMixin(UnifiedAccessMixin):
    """配色中心 — 基础权限管控"""
    user_link_fields = ['operator']
    identity_required = IdentityConfig.COLOR_TEAM

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return None
        user = self.request.user

        # 配色操作员按任务分配放宽数据可见范围
        if user.user_type in [IdentityConfig.R_COLOR_OP]:
            model = qs.model
            model_fields = [f.name for f in model._meta.get_fields()]
            if 'operator' in model_fields:
                from django.db.models import Q
                qs = qs.filter(
                    Q(operator=user) | Q(operator__isnull=True)
                )
        return qs

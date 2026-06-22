from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class TestingAccessMixin(UnifiedAccessMixin):
    """材料测试中心 — 基础权限管控"""
    user_link_fields = ['assigned_to']
    identity_required = IdentityConfig.TESTING_TEAM

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return None
        user = self.request.user

        # 测试操作员按任务分配放宽数据可见范围
        if user.user_type in [IdentityConfig.R_TESTING_OP]:
            model = qs.model
            model_fields = [f.name for f in model._meta.get_fields()]
            if 'assigned_to' in model_fields:
                from django.db.models import Q
                qs = qs.filter(
                    Q(assigned_to=user) | Q(assigned_to__isnull=True)
                )
        return qs

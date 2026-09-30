from django.db.models import Q

from app_user.mixins import UnifiedAccessMixin


class QuotationAccessMixin(UnifiedAccessMixin):
    """产品报价模块访问控制。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取；
    视图层逐视图声明 L3 permission_required。

    对象级权限在默认 L4/L5 隔离之上，额外放行审批流参与人
    （发起人 / 历史审批人 / 当前待办负责人或候选人），使跨部门审批能正常查看需求单。
    """
    module_code = 'quotation'
    module_name = '产品报价'
    module_description = '产品报价需求单。按发起人/销售员隔离，审批流参与人可查看。'
    user_link_fields = ['creator', 'salesperson']

    def check_object_permission(self, obj):
        user = self.request.user
        if user.is_superuser:
            return True

        # 数据所有者
        for attr in self.user_link_fields:
            if getattr(obj, f'{attr}_id', None) == user.pk:
                return True

        # 审批流参与人
        instance = getattr(obj, 'workflow_instance', None)
        if instance is not None:
            if instance.started_by_id == user.pk:
                return True
            if instance.history.filter(approver=user).exists():
                return True
            if instance.tasks.filter(status='PENDING').filter(
                Q(assigned_to=user) | Q(candidate_users=user),
            ).exists():
                return True

        # 兜底走 L4/L5 隔离
        return super().check_object_permission(obj)

from app_user.mixins import UnifiedAccessMixin


class ColorCenterAccessMixin(UnifiedAccessMixin):
    """配色中心基础准入管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    隔离维度按项目负责人（production_order.project.manager / project.manager），
    配色中心人员（命中 color_center.team）跳过 L4/L5。
    """

    module_code = 'color_center'
    module_name = '材料配色中心'
    module_description = '配色中心读侧。角色组配「配色中心人员 + 研发」；研发按项目负责人做 L4/L5 隔离，需 view_colormatchingtask。'
    user_link_fields = ['operator']  # 实际被 _resolve_owner / _isolation_field_name 覆盖

    def _isolation_field_name(self, model):
        """列表过滤的 owner 关联字段：按项目负责人。"""
        from app_project.models import Project
        from app_trial_production.models import ProductionOrder
        if model is ProductionOrder:
            return 'project__manager'
        if model is Project:
            return 'manager'
        return super()._isolation_field_name(model)

    def _resolve_owner(self, obj):
        """对象所有者 = 项目负责人（ProductionOrder → project.manager / Project → manager）。"""
        order = getattr(obj, 'project', None)
        if order is not None:
            return getattr(order, 'manager', None)
        return getattr(obj, 'manager', None)

    def check_object_permission(self, obj):
        # 配色中心人员：跳过 L4/L5（可见全部）
        if ColorCenterTeamAccessMixin.user_has_access(self.request.user):
            return True
        return super().check_object_permission(obj)


class ColorCenterTeamAccessMixin(ColorCenterAccessMixin):
    """配色中心人员身份标识 — 独立模块码注册，识别「跳过 L4/L5」。"""

    module_code = 'color_center.team'
    module_name = '材料配色中心-团队成员'
    module_description = '配色中心人员身份标识（仅识别跳过 L4/L5，不被视图继承）。仅配「配色中心人员」角色组。'


class ColorCenterReadMixin(ColorCenterAccessMixin):
    """配色中心读侧准入 — 继承基础准入（module_code='color_center'）。"""


class ColorCenterWriteMixin(ColorCenterReadMixin):
    """配色中心写侧准入 — 同读侧隔离规则，module_code 独立注册、独立控权。"""

    module_code = 'color_center.write'
    module_name = '材料配色中心-填写'
    module_description = '配色中心写侧。角色组配「配色中心人员 + 研发」；保存 BOM 需 change_colormatchingtask，隔离同读侧。'
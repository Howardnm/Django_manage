from app_user.mixins import UnifiedAccessMixin


class TestingAccessMixin(UnifiedAccessMixin):
    """材料测试中心基础准入管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    隔离维度按项目负责人（production_order.project.manager），
    测试中心人员（命中 material_testing.team）跳过 L4/L5。
    """

    module_code = 'material_testing'
    module_name = '材料测试中心'
    module_description = '材料测试中心（含列表/详情/写操作）。角色组配「测试中心人员 + 研发」；研发按项目负责人隔离，测试中心人员跳过 L4/L5。'
    user_link_fields = ['assigned_to']  # 实际被 _resolve_owner / _isolation_field_name 覆盖

    def _resolve_owner(self, obj):
        """对象所有者 = 测试任务关联项目的负责人（跨关系路径）。"""
        order = getattr(obj, 'production_order', None)
        project = getattr(order, 'project', None) if order else None
        return getattr(project, 'manager', None) if project else None

    def _isolation_field_name(self, model):
        """列表过滤的 owner 关联字段：按项目负责人。"""
        from app_material_testing.models import TestingTask
        if model is TestingTask:
            return 'production_order__project__manager'
        return super()._isolation_field_name(model)

    def check_object_permission(self, obj):
        # 测试中心人员：跳过 L4/L5（可见全部任务）
        if TestingTeamAccessMixin.user_has_access(self.request.user):
            return True
        return super().check_object_permission(obj)


class TestingTeamAccessMixin(TestingAccessMixin):
    """测试中心人员身份标识 — 独立模块码注册，识别「跳过 L4/L5」。

    本 mixin 仅作「是否为测试中心团队成员」的身份判断载体，不被视图继承；
    由 TestingAccessMixin.check_object_permission 通过 user_has_access 调用。
    """

    module_code = 'material_testing.team'
    module_name = '材料测试中心-团队成员'
    module_description = '测试中心人员身份标识（仅识别跳过 L4/L5，不被视图继承）。仅配「测试中心人员」角色组。'


class TestingTaskAccessMixin(TestingAccessMixin):
    """测试任务列表/详情页权限 — 继承基础准入的所有隔离逻辑。

    独立 module_code（material_testing.task），管理员可单独控制列表/详情页的 L4/L5 隔离。
    """

    module_code = 'material_testing.task'
    module_name = '材料测试中心-测试任务'
    module_description = '测试任务列表/详情页。角色组配「测试中心人员 + 研发」；研发按项目负责人隔离，测试中心人员跳过 L4/L5。'
from app_user.mixins import UnifiedAccessMixin


class TestingAccessMixin(UnifiedAccessMixin):
    """材料测试中心权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    操作员数据视野放宽逻辑已移除——角色通过 ModuleAccessConfig 分配后自然有权访问。
    """

    module_code = 'material_testing'
    module_name = '材料测试中心'
    module_description = '材料测试中心。角色组配「测试中心人员 + 研发」；研发按项目负责人隔离，需 view/change_testingtask。'
    user_link_fields = ['assigned_to']


class TestingTeamAccessMixin(TestingAccessMixin):
    """测试中心人员身份标识 — 独立模块码注册，供详情页识别跳过 L4/L5。

    本 mixin 仅作「是否为测试中心团队成员」的身份判断载体，不被视图继承；
    由 TestingDetailAccessMixin.check_object_permission 通过 user_has_access 调用。
    """

    module_code = 'material_testing.team'
    module_name = '材料测试中心-团队成员'
    module_description = '测试中心人员身份标识（仅识别跳过 L4/L5，不被视图继承）。仅配「测试中心人员」角色组。'


class TestingDetailAccessMixin(TestingAccessMixin):
    """测试任务详情页权限 — 研发按项目负责人隔离，测试中心人员跳过 L4/L5。

    数据所有者 = 测试任务关联项目的负责人（production_order.project.manager），
    而非 assigned_to（测试员），使「研发角色组被授权后按项目负责人做部门/工作组隔离」成立。
    """

    def _resolve_owner(self, obj):
        """数据所有者 = 测试任务关联项目的负责人（跨关系路径）。"""
        order = getattr(obj, 'production_order', None)
        project = getattr(order, 'project', None) if order else None
        return getattr(project, 'manager', None) if project else None

    def check_object_permission(self, obj):
        # 测试中心人员：跳过 L4/L5（可见全部任务）
        if TestingTeamAccessMixin.user_has_access(self.request.user):
            return True
        return super().check_object_permission(obj)
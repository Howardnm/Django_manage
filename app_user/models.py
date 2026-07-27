"""app_user 数据模型。

导出: UserRole, RoleGroup, ModuleAccessConfig, SidebarModule, SidebarSubItem,
      PermissionGroup, Subsidiary, Department, OrgRole,
      OrgRoleAssignment, ReviewGroup, WorkGroup, User。"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, Group as AuthGroup


class PermissionGroup(AuthGroup):
    """[L3 权限容器] Django 原生权限组：管理各模块的增删改查权限码，在准入链最后被校验。"""
    class Meta:
        proxy = True
        app_label = 'app_user'
        verbose_name = '[L3 权限容器] 权限角色组'
        verbose_name_plural = '[L3 权限容器] 权限角色组'


class Subsidiary(models.Model):
    """子公司/基地模型。用于标识员工所属的法人实体或办公基地，便于按子公司维度统计。"""
    name = models.CharField("子公司名称", max_length=50, unique=True)
    code = models.CharField("子公司编码", max_length=20, blank=True, help_text="用于系统内部逻辑识别")
    description = models.TextField("描述", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "子公司/基地"
        verbose_name_plural = "子公司/基地"
        ordering = ['name']

    def __str__(self):
        """返回子公司名称。"""
        return self.name


class Department(models.Model):
    """
    组织架构/部门模型
    用于逻辑分组，控制数据隔离
    """
    name = models.CharField("部门名称", max_length=50, unique=True)
    code = models.CharField("部门编码", max_length=20, blank=True, help_text="用于系统内部逻辑识别")
    description = models.TextField("部门描述", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """返回部门名称。"""
        return self.name

    class Meta:
        verbose_name = "[L4] 部门"
        verbose_name_plural = "[L4] 部门"


class OrgRole(models.Model):
    """组织角色定义。定义"组长"、"部门经理"、"基地总经理"等角色及其查找作用域。
    BPMN 工作流通过 WorkflowTaskConfig 关联到此处定义的角色编码。"""

    class Scope(models.TextChoices):
        WORKGROUP = 'workgroup', '工作组级 — 在发起人的工作组中查找该角色'
        DEPARTMENT = 'department', '部门级 — 在发起人的部门中查找该角色'
        SUBSIDIARY = 'subsidiary', '子公司/基地级 — 在发起人的子公司中查找该角色'

    code = models.CharField(
        "角色编码", max_length=50, unique=True,
        help_text=(
            "① 全局唯一标识符，建议用小写英文下划线命名。"
            "② 例如：'group_leader'（组长）、'dept_manager'（部门经理）、'subsidiary_gm'（基地总经理）。"
            "③ 此编码将在 WorkflowTaskConfig 中被引用，请保持稳定不变。"
        ))
    name = models.CharField(
        "角色名称", max_length=50,
        help_text=(
            "① 显示用中文名称。"
            "② 例如：'组长'、'部门经理'、'基地总经理'。"
            "③ 此名称会出现在 Admin 下拉框和列表页中。"
        ))
    scope = models.CharField(
        "查找作用域", max_length=20, choices=Scope.choices,
        help_text=(
            "① 决定引擎在哪个组织层级查找该角色的负责人。\n"
            "② 工作组级：在工作流发起人所属的工作组中查找。\n"
            "③ 部门级：在发起人所属的部门中查找。\n"
            "④ 子公司级：在发起人所属的子公司/基地中查找。\n"
            "⑤ #操作指引：创建角色时，先想清楚这个角色的审批范围是什么层级。"
        ))
    allow_escalation = models.BooleanField(
        "允许逐级向上回退", default=True,
        help_text=(
            "① 开启后，如果在当前作用域找不到指派人，引擎会自动向上一级查找。\n"
            "② 回退链路：工作组 → 部门 → 子公司。\n"
            "③ 例如：「组长」scope=工作组级，某工作组未指派组长时 → 自动在部门级查找 → 仍未找到则在子公司级查找。\n"
            "④ 关闭后，找不到即返回空，走后续的 BPMN 属性 / 发起人兜底逻辑。\n"
            "⑤ #建议：一般保持开启，避免因某个组织单元漏配而导致审批中断。"
        ))
    description = models.TextField(
        "描述", blank=True,
        help_text="可选。补充说明该角色的审批职责和适用范围。")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[审批] 组织角色"
        verbose_name_plural = "[审批] 组织角色"
        ordering = ['scope', 'name']

    def __str__(self):
        """返回 '[作用域] 角色名称' 格式。"""
        return f"[{self.get_scope_display()}] {self.name}"


class OrgRoleAssignment(models.Model):
    """用户在特定组织单元中的角色指派。
    例如: 张三 在 配方组 担任 组长；李四 在 研发中心 担任 部门经理。"""

    role = models.ForeignKey(
        OrgRole, on_delete=models.CASCADE, verbose_name="角色",
        help_text=(
            "① 选择要指派的组织角色。\n"
            "② 所选角色的「查找作用域」决定了你需要填写下方哪个组织单元字段。\n"
            "③ #操作指引：先在上方「组织角色」中定义好角色，再来这里做人员指派。"
        ))
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE,
        related_name='org_role_assignments', verbose_name="用户",
        help_text="被指派为该角色负责人的用户。")

    # 三级作用域 — 根据 role.scope 决定填写哪个字段
    subsidiary = models.ForeignKey(
        'Subsidiary', on_delete=models.CASCADE,
        null=True, blank=True, verbose_name="所属子公司",
        help_text=(
            "① 仅当角色的「查找作用域」为「子公司级」时需要填写。\n"
            "② 例如：角色=基地总经理，此处选择「上海总部」。\n"
            "③ #操作指引：先在下方「子公司/基地」管理中创建子公司记录。"
        ))
    department = models.ForeignKey(
        'Department', on_delete=models.CASCADE,
        null=True, blank=True, verbose_name="所属部门",
        help_text=(
            "① 仅当角色的「查找作用域」为「部门级」时需要填写。\n"
            "② 例如：角色=部门经理，此处选择「研发中心」。\n"
            "③ #操作指引：先在下方「[L4] 部门」管理中创建部门记录。"
        ))
    workgroup = models.ForeignKey(
        'WorkGroup', on_delete=models.CASCADE,
        null=True, blank=True, verbose_name="所属工作组",
        help_text=(
            "① 仅当角色的「查找作用域」为「工作组级」时需要填写。\n"
            "② 例如：角色=组长，此处选择「配方组」。\n"
            "③ #操作指引：先在下方「[L5] 工作组」管理中创建工作组记录。"
        ))

    is_primary = models.BooleanField(
        "主负责人", default=True,
        help_text=(
            "① 同一角色在同一组织单元可以有多个指派（如正副职）。\n"
            "② 勾选「主负责人」的用户会优先被引擎匹配。\n"
            "③ 如果该角色只需要一个人，保持勾选即可。"
        ))
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[审批] 组织角色指派"
        verbose_name_plural = "[审批] 组织角色指派"
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'user', 'subsidiary'],
                name='unique_role_user_subsidiary',
                condition=models.Q(subsidiary__isnull=False)),
            models.UniqueConstraint(
                fields=['role', 'user', 'department'],
                name='unique_role_user_department',
                condition=models.Q(department__isnull=False)),
            models.UniqueConstraint(
                fields=['role', 'user', 'workgroup'],
                name='unique_role_user_workgroup',
                condition=models.Q(workgroup__isnull=False)),
        ]

    def clean(self):
        """校验：填写的组织单元层级必须匹配 role.scope。"""
        from django.core.exceptions import ValidationError
        if self.role.scope == 'workgroup' and not self.workgroup:
            raise ValidationError("工作组级角色必须指定 workgroup")
        if self.role.scope == 'department' and not self.department:
            raise ValidationError("部门级角色必须指定 department")
        if self.role.scope == 'subsidiary' and not self.subsidiary:
            raise ValidationError("子公司级角色必须指定 subsidiary")

    def __str__(self):
        """返回 '组织单元 → 角色: 用户名' 格式。"""
        unit = self.workgroup or self.department or self.subsidiary
        return f"{unit} → {self.role.name}: {self.user.username}"


class ReviewGroup(models.Model):
    """审核组：为工作流审批提供可管理的用户分组。"""
    name = models.CharField("组名称", max_length=150, unique=True)
    description = models.TextField("描述", blank=True)
    members = models.ManyToManyField(
        'User',
        related_name='review_groups',
        blank=True,
        verbose_name="组成员",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="所属部门",
        help_text="限定该审核组的部门作用域（留空表示跨部门）",
    )
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "[审批] 审核组"
        verbose_name_plural = "[审批] 审核组"
        ordering = ['name']

    def __str__(self):
        """返回审核组名称。"""
        return self.name


class WorkGroup(models.Model):
    """工作组：部门内部的团队划分，用于 L5 数据资产隔离。"""
    name = models.CharField("组名称", max_length=150)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        verbose_name="所属部门",
    )
    members = models.ManyToManyField(
        'User',
        related_name='work_groups',
        blank=True,
        verbose_name="组成员",
    )
    description = models.TextField("描述", blank=True)
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "[L5] 工作组"
        verbose_name_plural = "[L5] 工作组"
        ordering = ['department', 'name']
        unique_together = [('name', 'department')]

    def __str__(self):
        """返回 "[部门] 名称" 格式的字符串。"""
        return f"[{self.department.name}] {self.name}"


class UserRole(models.Model):
    """[L1] 用户角色定义 — 替代原 User.UserType 枚举。

    每个角色对应一个唯一的 code，作为权限判断的标识符。
    Admin 可随时新增、禁用角色，无需改代码或 migration。
    """
    code = models.CharField("角色编码", max_length=50, primary_key=True,
                            help_text="全局唯一标识符，如 'ENGINEER'、'SALES'。")
    name = models.CharField("角色名称", max_length=50,
                            help_text="如 '研发工程师'、'业务员'。")
    is_internal = models.BooleanField("内部角色", default=True,
                                      help_text="内部员工角色可登录管理系统；外部角色（客户/OEM）仅可访问电子手册。")
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[L1] 用户角色"
        verbose_name_plural = "[L1] 用户角色"
        ordering = ['sort_order', 'code']

    def __eq__(self, other):
        """支持与字符串比较: user.user_type == 'ENGINEER' 正常工作。"""
        if isinstance(other, str):
            return self.code == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.code)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    自定义用户模型，集成了研发、工艺、销售、采购、管理等核心业务角色。
    """
    # --- 1. 核心权限决策字段 ---
    user_type = models.ForeignKey(
        UserRole, on_delete=models.PROTECT, verbose_name="用户角色",
        help_text="决定 L1 角色白名单准入权限。")
    user_level = models.PositiveIntegerField("用户等级", default=1)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所属部门")
    subsidiary = models.ForeignKey(
        'Subsidiary',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="所属子公司/基地",
        help_text="员工所在的子公司或办公基地（仅用于统计，不影响权限）",
    )

    # --- 外部系统核心识别码 (从业务表迁移至此) ---
    member_token = models.UUIDField("外部唯一令牌", default=uuid.uuid4, editable=False, unique=True)

    # --- 公司归属关联 ---
    associated_customer = models.ForeignKey('app_repository.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='members', verbose_name="所属客户公司")
    associated_oem = models.ForeignKey('app_repository.OEM', on_delete=models.SET_NULL, null=True, blank=True, related_name='members', verbose_name="所属主机厂")

    job_title = models.CharField("职称/职位", max_length=50, blank=True)
    phone = models.CharField("个人电话", max_length=20, blank=True)
    email = models.EmailField("电子邮箱", blank=True)  # 未设置 unique=True：历史数据可能存在多用户共享邮箱的情况
    address = models.CharField("联系地址", max_length=255, blank=True)
    description = models.TextField("个人备注", blank=True)

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def __str__(self):
        """返回 "[部门] 角色 - 用户名" 格式。"""
        dept_str = f"[{self.department.name}]" if self.department else ""
        role_name = self.user_type.name if self.user_type_id else '未分配角色'
        return f"{dept_str} {role_name} - {self.username}"


# ============================================================
# 动态 RBAC 权限体系 — 以下模型替代原硬编码的 IdentityConfig / MenuModule / init_permissions
# ============================================================

class RoleGroup(models.Model):
    """[L1 分组] 角色分组 — 替代原 IdentityConfig 静态常量。

    将多个 UserRole 归入一个命名的权限组（如 TECH_CORE、RND_ONLY），
    然后通过 ModuleAccessConfig 分配给各业务模块。
    """
    code = models.CharField("分组编码", max_length=50, unique=True,
                            help_text="如 'TECH_CORE'、'RND_ONLY'。")
    name = models.CharField("分组名称", max_length=50,
                            help_text="如 '技术核心组'、'纯研发组'。")
    description = models.TextField("描述", blank=True)
    roles = models.ManyToManyField(UserRole, verbose_name="包含角色",
                                   related_name='groups')
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[L1 分组] 角色分组"
        verbose_name_plural = "[L1 分组] 角色分组"
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"


class ModuleAccessConfig(models.Model):
    """[L1~L5 配置] 模块权限配置 — 核心枢纽。

    每个业务模块对应一条记录，声明：
    - 哪些 RoleGroup 可以访问（L1）
    - 最低用户等级（L2）
    - 是否启用部门隔离（L4）
    - 是否启用工作组隔离（L5）

    mixin 通过 module_code 查找对应记录，动态获取全部权限配置。
    """
    module_code = models.CharField("模块编码", max_length=80, unique=True,
                                   help_text="如 'formula'、'trial_production.extrusion_task'。")
    module_name = models.CharField("模块名称", max_length=50,
                                   help_text="如 '实验配方库'。")
    role_groups = models.ManyToManyField(RoleGroup, verbose_name="允许访问的角色组",
                                         help_text="用户所属角色在任一勾选组中即可访问本模块。")
    min_level = models.PositiveIntegerField("最低等级", default=1,
                                            help_text="L2 用户等级门槛。")
    enforce_dept_isolation = models.BooleanField("部门隔离 (L4)", default=True)
    enforce_group_isolation = models.BooleanField("工作组隔离 (L5)", default=False)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[L1~L5] 模块权限配置"
        verbose_name_plural = "[L1~L5] 模块权限配置"
        ordering = ['module_code']

    def __str__(self):
        return f"{self.module_name} ({self.module_code})"


class SidebarModule(models.Model):
    """[菜单] 侧边栏模块 — 替代原 MenuModule.get_*() 静态方法。

    每个顶级菜单项对应一条记录，通过 module_access 关联到 ModuleAccessConfig，
    共用同一套 L1 角色白名单，确保菜单可见性与视图层权限一致。
    """
    code = models.CharField("菜单编码", max_length=50, unique=True,
                            help_text="如 'dashboard'、'formula'。")
    name = models.CharField("菜单名称", max_length=50)
    icon = models.CharField("图标", max_length=50,
                            help_text="Tabler Icons 类名，不含 'ti-' 前缀，如 'ti-test-pipe' 写 'test-pipe'。")
    url_name = models.CharField("URL 名称", max_length=200,
                                help_text="Django URL name，用于 reverse() 解析。")
    module_access = models.ForeignKey(ModuleAccessConfig, on_delete=models.SET_NULL,
                                      null=True, blank=True, verbose_name="关联权限配置",
                                      help_text="共用 ModuleAccessConfig 的 L1 角色白名单。")
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "[菜单] 侧边栏模块"
        verbose_name_plural = "[菜单] 侧边栏模块"
        ordering = ['sort_order', 'code']

    def __str__(self):
        return self.name


class SidebarSubItem(models.Model):
    """[菜单] 侧边栏子项 — 替代原子菜单 dict。

    支持独立覆盖 L1（窄于模块级）、L2（min_level）、L3（Django 权限码）。
    """
    module = models.ForeignKey(SidebarModule, on_delete=models.CASCADE,
                               related_name='sub_items', verbose_name="所属模块")
    name = models.CharField("子项名称", max_length=50)
    url_name = models.CharField("URL 名称", max_length=200)
    role_group = models.ForeignKey(RoleGroup, on_delete=models.SET_NULL,
                                   null=True, blank=True, verbose_name="L1 角色覆盖",
                                   help_text="留空则继承父模块的可见角色。")
    min_level = models.PositiveIntegerField("最低等级 (L2)", null=True, blank=True,
                                            help_text="留空则不检查等级。")
    permissions = models.JSONField("权限码 (L3)", default=list, blank=True,
                                   help_text="Django 权限码列表，如 ['app_formula.view_labformula']。")
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "[菜单] 侧边栏子项"
        verbose_name_plural = "[菜单] 侧边栏子项"
        ordering = ['module', 'sort_order']

    def __str__(self):
        return f"{self.module.name} > {self.name}"



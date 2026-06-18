"""app_user 数据模型。定义 User、Department、WorkGroup、ReviewGroup、PermissionGroup。

导出: PermissionGroup, Department, ReviewGroup, WorkGroup, User。"""

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


class User(AbstractUser):
    """
    自定义用户模型，集成了研发、工艺、销售、采购、管理等核心业务角色。
    """
    class UserType(models.TextChoices):
        """用户角色枚举，与 IdentityConfig 分组常量对应。"""
        ENGINEER = 'ENGINEER', '研发工程师'
        PROCESS_ENGINEER = 'PROCESS_ENGINEER', '工艺工程师'
        SALES = 'SALES', '业务员'
        PURCHASING = 'PURCHASING', '采购专员'
        CUSTOMER = 'CUSTOMER', '外部客户'
        OEM = 'OEM', '主机厂成员'
        ADMIN = 'ADMIN', '系统管理员'
        EXTRUSION_OPERATOR = 'EXTRUSION_OPERATOR', '挤出操作员'
        COLOR_OPERATOR = 'COLOR_OPERATOR', '配色员'
        INJECTION_OPERATOR = 'INJECTION_OPERATOR', '注塑操作员'
        TESTING_OPERATOR = 'TESTING_OPERATOR', '测试员'

    # --- 1. 核心权限决策字段 ---
    user_type = models.CharField("用户角色", max_length=20, choices=UserType.choices, default=UserType.ENGINEER)
    user_level = models.PositiveIntegerField("用户等级", default=1)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所属部门")
    
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
        return f"{dept_str} {self.get_user_type_display()} - {self.username}"

    # --- 快捷权限判断方法 (用于模板) ---
    @property
    def is_engineer(self):
        """是否为研发工程师。"""
        return self.user_type == self.UserType.ENGINEER
    @property
    def is_process_engineer(self):
        """是否为工艺工程师。"""
        return self.user_type == self.UserType.PROCESS_ENGINEER
    @property
    def can_use_compare_cart(self):
        """配方对比购物车准入：仅研发工程师 + 管理员（RND_ONLY）"""
        return self.is_engineer or self.user_type == self.UserType.ADMIN or self.is_superuser
    @property
    def is_sales(self):
        """是否为业务员。"""
        return self.user_type == self.UserType.SALES

    @property
    def is_purchasing(self):
        """是否为采购专员。"""
        return self.user_type == self.UserType.PURCHASING

    @property
    def is_external(self):
        """是否为客户或 OEM 外部角色。"""
        return self.user_type in [self.UserType.CUSTOMER, self.UserType.OEM]
    @property
    def is_extrusion_operator(self):
        """是否为挤出操作员。"""
        return self.user_type == self.UserType.EXTRUSION_OPERATOR

    @property
    def is_color_operator(self):
        """是否为配色员。"""
        return self.user_type == self.UserType.COLOR_OPERATOR

    @property
    def is_injection_operator(self):
        """是否为注塑操作员。"""
        return self.user_type == self.UserType.INJECTION_OPERATOR

    @property
    def is_testing_operator(self):
        """是否为测试员。"""
        return self.user_type == self.UserType.TESTING_OPERATOR

    @property
    def is_admin(self):
        """是否为系统管理员。"""
        return self.user_type == self.UserType.ADMIN

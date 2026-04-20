import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

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
        return self.name

    class Meta:
        verbose_name = "部门"
        verbose_name_plural = "部门管理"


class User(AbstractUser):
    """
    自定义用户模型，集成了研发、工艺、销售、采购、管理等核心业务角色。
    """
    class UserType(models.TextChoices):
        ENGINEER = 'ENGINEER', '研发工程师'
        PROCESS_ENGINEER = 'PROCESS_ENGINEER', '工艺工程师'
        SALES = 'SALES', '业务经理'
        PURCHASING = 'PURCHASING', '采购专员'
        CUSTOMER = 'CUSTOMER', '外部客户'
        OEM = 'OEM', '主机厂成员'
        ADMIN = 'ADMIN', '系统管理员'

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
    email = models.EmailField("电子邮箱", blank=True)
    address = models.CharField("联系地址", max_length=255, blank=True)
    description = models.TextField("个人备注", blank=True)

    class Meta:
        verbose_name = "用户信息"
        verbose_name_plural = "用户信息"

    def __str__(self):
        dept_str = f"[{self.department.name}]" if self.department else ""
        return f"{dept_str} {self.get_user_type_display()} - {self.username}"

    # --- 快捷权限判断方法 (用于模板) ---
    @property
    def is_engineer(self): return self.user_type == self.UserType.ENGINEER
    @property
    def is_process_engineer(self): return self.user_type == self.UserType.PROCESS_ENGINEER
    @property
    def is_sales(self): return self.user_type == self.UserType.SALES
    @property
    def is_purchasing(self): return self.user_type == self.UserType.PURCHASING
    @property
    def is_external(self): return self.user_type in [self.UserType.CUSTOMER, self.UserType.OEM]

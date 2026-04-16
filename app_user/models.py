from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """
    自定义用户模型，统一管理工程师、业务员、客户、OEM成员。
    """
    class UserType(models.TextChoices):
        ENGINEER = 'ENGINEER', '研发工程师'
        SALES = 'SALES', '业务经理'
        CUSTOMER = 'CUSTOMER', '外部客户'
        OEM = 'OEM', '主机厂成员'
        ADMIN = 'ADMIN', '系统管理员'

    # 1. 核心角色与等级
    user_type = models.CharField("用户角色", max_length=20, choices=UserType.choices, default=UserType.ENGINEER)
    user_level = models.PositiveIntegerField("用户等级", default=1)
    
    # 2. 扩展个人信息
    job_title = models.CharField("职称/职位", max_length=50, blank=True)
    company = models.CharField("所属公司/部门", max_length=100, blank=True)
    phone = models.CharField("手机号码", max_length=20, blank=True)
    email = models.EmailField("电子邮箱", blank=True)
    address = models.CharField("联系地址", max_length=255, blank=True)
    description = models.TextField("个人/公司描述", blank=True)

    class Meta:
        verbose_name = "用户信息"
        verbose_name_plural = "用户信息"

    def __str__(self):
        return f"{self.get_user_type_display()} - {self.username}"

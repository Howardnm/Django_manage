from django.db import models

class CatalogMember(models.Model):
    """
    手册系统会员镜像：仅存储基础身份标识。
    核心原则：最小化数据存储，不保存任何敏感或冗余权限字段。
    """
    ROLE_CHOICES = [
        ('CUSTOMER', '直接客户'),
        ('OEM', '主机厂'),
        ('STAFF', '内部员工'),
    ]

    # --- 核心标识 ---
    remote_member_token = models.CharField("主系统令牌", max_length=100, unique=True)
    display_name = models.CharField("名称", max_length=100, blank=True)
    role = models.CharField("访问角色", max_length=20, choices=ROLE_CHOICES, default='CUSTOMER')
    
    # --- 状态控制 ---
    is_active = models.BooleanField("有效状态", default=True)
    last_synced_at = models.DateTimeField("同步时间", auto_now=True)

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"

    class Meta:
        verbose_name = "手册会员镜像"
        verbose_name_plural = "3.会员镜像库"

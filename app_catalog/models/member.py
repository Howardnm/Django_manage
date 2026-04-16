from django.db import models

class CatalogMember(models.Model):
    """
    手册系统会员镜像：存储从主系统同步过来的会员身份信息。
    支持独立部署时的离线鉴权和身份识别。
    """
    ROLE_CHOICES = [
        ('CUSTOMER', '直接客户'),
        ('OEM', '主机厂'),
        ('STAFF', '内部员工 (业务员)'),
    ]

    # 主系统中的唯一标识 (Member Token)
    remote_member_token = models.UUIDField("主系统唯一令牌", unique=True)
    
    # 登录名镜像 (同步主系统的 User.username)
    username = models.CharField("用户名镜像", max_length=150, unique=True)
    
    # 基本信息冗余
    display_name = models.CharField("显示名称", max_length=100) # 公司名或姓名
    email = models.EmailField("邮箱镜像", blank=True)
    role = models.CharField("会员角色", max_length=20, choices=ROLE_CHOICES, default='CUSTOMER')
    
    # 状态控制
    is_active = models.BooleanField("账号有效状态", default=True)
    last_synced_at = models.DateTimeField("最后同步时间", auto_now=True)

    def __str__(self):
        return f"{self.display_name} ({self.role})"

    class Meta:
        verbose_name = "手册会员镜像"
        verbose_name_plural = "3.会员镜像库"

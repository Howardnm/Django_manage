from django.db import models
from .catalog import CatalogProduct

class VisitorLog(models.Model):
    """
    访客日志：记录用户行为。
    升级版：支持记录登录会员的唯一令牌。
    """
    ACTION_CHOICES = [
        ('VIEW', '查看详情'),
        ('DOWNLOAD', '下载文档'),
        ('SEARCH', '搜索'),
    ]

    product = models.ForeignKey(CatalogProduct, on_delete=models.CASCADE, null=True, blank=True)
    visitor_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # 核心字段：记录主系统同步过来的成员令牌 (如果是登录状态)
    member_token = models.CharField("会员令牌", max_length=100, null=True, blank=True, db_index=True)
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='VIEW')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_desc = self.member_token if self.member_token else self.visitor_ip
        return f"{user_desc} - {self.action} - {self.timestamp}"

    class Meta:
        verbose_name = "访客日志"
        verbose_name_plural = "4.访客日志记录"
        ordering = ['-timestamp']

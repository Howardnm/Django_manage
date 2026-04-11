from django.db import models
from .catalog import CatalogProduct

class VisitorLog(models.Model):
    """访客记录：用于追踪客户查看和下载行为"""
    product = models.ForeignKey(CatalogProduct, on_delete=models.CASCADE)
    visitor_ip = models.GenericIPAddressField("访客IP")
    user_agent = models.TextField("浏览器标识", blank=True)
    action = models.CharField("动作", max_length=20, choices=[('VIEW', '查看'), ('DOWNLOAD', '下载')])
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "访客记录"
        verbose_name_plural = "3.访客记录详情"

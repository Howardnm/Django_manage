"""SAP 连接配置模型 — 支持通过数据库动态覆盖 settings 中的连接参数"""

from django.db import models


class SapConnectionConfig(models.Model):
    """SAP 连接配置（可选：当需要数据库管理连接参数时使用，优先级高于 settings）"""

    name = models.CharField(max_length=100, verbose_name='配置名称', default='default')
    ashost = models.CharField(max_length=255, verbose_name='SAP 主机地址')
    sysnr = models.CharField(max_length=2, verbose_name='系统编号', default='00')
    client = models.CharField(max_length=3, verbose_name='客户端', default='800')
    user = models.CharField(max_length=50, verbose_name='用户名')
    passwd = models.CharField(max_length=128, verbose_name='密码')
    lang = models.CharField(max_length=2, verbose_name='语言', default='ZH')

    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'sap_connection_config'
        verbose_name = 'SAP连接配置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.name} ({self.user}@{self.ashost})'

"""SAP 数据同步日志 — 记录每次从 SAP 拉取数据的操作"""

from django.db import models


class SapSyncLog(models.Model):
    """SAP 数据同步操作日志"""

    FUNCTION_CHOICES = [
        ('MATERIAL', '物料主数据'),
        ('BOM', 'BOM清单'),
        ('VENDOR', '供应商'),
        ('CUSTOMER', '客户'),
        ('ORDER', '生产订单'),
        ('PRICE', '价格'),
        ('OTHER', '其他'),
    ]

    STATUS_CHOICES = [
        ('SUCCESS', '成功'),
        ('FAILED', '失败'),
        ('PARTIAL', '部分成功'),
    ]

    function_type = models.CharField(
        max_length=50, choices=FUNCTION_CHOICES, verbose_name='同步类型',
    )
    rfc_name = models.CharField(max_length=100, verbose_name='RFC 函数名')
    request_params = models.JSONField(default=dict, verbose_name='请求参数')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, verbose_name='同步状态',
    )
    records_fetched = models.IntegerField(default=0, verbose_name='获取记录数')
    records_synced = models.IntegerField(default=0, verbose_name='同步记录数')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    duration_ms = models.IntegerField(default=0, verbose_name='耗时(毫秒)')

    triggered_by = models.ForeignKey(
        'app_user.User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='触发人',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'sap_sync_log'
        verbose_name = 'SAP同步日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_function_type_display()} - {self.created_at:%Y-%m-%d %H:%M}'

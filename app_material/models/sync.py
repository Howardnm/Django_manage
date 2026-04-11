from django.db import models

class WebhookTask(models.Model):
    """Webhook 异步任务队列：记录对外同步任务的状态和重试情况"""
    STATUS_CHOICES = [
        ('PENDING', '等待中'),
        ('PROCESSING', '处理中'),
        ('SUCCESS', '成功'),
        ('FAILED', '失败'),
    ]

    event_type = models.CharField("事件类型", max_length=50)
    payload = models.TextField("任务数据 (JSON)")
    
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    retry_count = models.PositiveIntegerField("重试次数", default=0)
    max_retries = models.PositiveIntegerField("最大重试次数", default=5)
    
    last_error = models.TextField("最后错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后更新时间", auto_now=True)

    def __str__(self):
        return f"Task {self.id}: {self.event_type} ({self.status})"

    class Meta:
        verbose_name = "Webhook同步任务"
        verbose_name_plural = "Webhook任务监控"
        ordering = ['created_at']

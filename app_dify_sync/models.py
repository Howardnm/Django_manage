import hashlib
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class DifySyncRecord(models.Model):
    """
    一个用于追踪 Django 项目中各种数据对象与 Dify 知识库同步状态的模型。
    """
    class SyncStatus(models.TextChoices):
        PENDING = 'PENDING', '待同步'
        SYNCING = 'SYNCING', '同步中'
        COMPLETED = 'COMPLETED', '已完成'
        FAILED = 'FAILED', '失败'
        OUTDATED = 'OUTDATED', '已过期' # 源数据已更新，需要重新同步
        DELETED = 'DELETED', '待删除' # 源数据已删除，需要从Dify删除

    # --- 关联到项目中的源数据对象 ---
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # --- Dify 相关信息 ---
    dify_dataset_id = models.CharField("Dify 数据集ID", max_length=100, blank=True, null=True, db_index=True)
    dify_document_id = models.CharField("Dify 文档ID", max_length=100, unique=True, blank=True, null=True, help_text="同步成功后由Dify返回的唯一标识")

    # --- 同步状态与日志 ---
    status = models.CharField("同步状态", max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING, db_index=True)
    last_sync_at = models.DateTimeField("上次同步时间", null=True, blank=True)
    last_success_at = models.DateTimeField("上次成功时间", null=True, blank=True)
    error_message = models.TextField("错误信息", blank=True, null=True)
    
    # --- 用于检测数据变更 ---
    source_hash = models.CharField("源数据哈希", max_length=64, blank=True, null=True, help_text="用于快速检测源数据是否变化")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dify 同步记录"
        verbose_name_plural = "Dify 同步记录"
        ordering = ['-updated_at']
        # 创建联合索引以加速通过 content_object 查找记录
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]
        # 确保每个源对象只有一条同步记录
        unique_together = ('content_type', 'object_id')

    def __str__(self):
        return f"Sync record for {self.content_object} ({self.status})"

    def calculate_hash(self, data_string):
        """计算并返回给定字符串的 SHA-256 哈希值"""
        return hashlib.sha256(data_string.encode('utf-8')).hexdigest()

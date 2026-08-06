from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    """
    通用通知模型
    说明: [actor] [verb] [target] (e.g., "张三 更新了进度节点 '节点A'")
    type 为通知类型编码（registry 中注册），url/title/icon 为创建时快照，
    模板只读快照字段，避免对任意 target 的硬编码属性访问。
    """
    CHANNEL_CHOICES = [
        ('inbox', '站内信'),   # 预留渠道扩展（邮件/企业微信等）
    ]

    # 通知接收者
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', verbose_name="接收者")

    # 动作发起者 (可以为空，例如系统通知)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='actions', verbose_name="发起者")

    # 描述动作的短语
    verb = models.CharField(max_length=255, verbose_name="动作")

    # --- 通用外键 (GenericForeignKey)，用于指向任何模型对象 ---
    # 1. 动作的目标 (可以为空)
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, related_name='target_notifications')
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')

    # 2. 动作发生的上下文 (例如，在哪个项目里产生了评论)
    action_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, related_name='action_object_notifications')
    action_object_object_id = models.PositiveIntegerField(null=True, blank=True)
    action_object = GenericForeignKey('action_object_content_type', 'action_object_object_id')
    # --- End of GenericForeignKey ---

    # 通知类型编码（registry 中注册，用于分类/筛选/偏好/渲染）
    type = models.CharField("通知类型", max_length=50, db_index=True, default='generic')
    # 渠道（预留扩展，当前仅站内信）
    channel = models.CharField("渠道", max_length=20, choices=CHANNEL_CHOICES, default='inbox')
    # 落地页 URL（创建时快照，点击通知跳转）
    url = models.CharField("落地页", max_length=500, blank=True, default='')
    # 标题 & 图标（创建时快照，模板渲染用）
    title = models.CharField("标题", max_length=255, blank=True, default='')
    icon = models.CharField("图标", max_length=50, blank=True, default='')

    # 状态和时间戳
    unread = models.BooleanField(default=True, db_index=True, verbose_name="是否未读")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="时间戳")

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知中心"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['recipient', 'unread', 'timestamp'],
                         name='notif_recip_unread_ts_idx'),
        ]

    def __str__(self):
        if self.target:
            return f'{self.actor} {self.verb} {self.target}'
        return f'{self.actor} {self.verb}'

    @property
    def type_label(self):
        """通知类型显示名（懒加载，避免循环导入）。"""
        from .registry import get_ntype
        t = get_ntype(self.type)
        return t.label if t else self.type

    @property
    def type_icon(self):
        """通知类型图标（回退到快照字段）。"""
        return self.icon or 'ti-bell'

    def mark_as_read(self):
        if self.unread:
            self.unread = False
            self.save()
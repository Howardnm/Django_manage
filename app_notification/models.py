from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    """
    通用通知模型
    范例: [actor] [verb] [target] (e.g., "张三 更新了项目 '项目A'")
         [actor] [verb] (e.g., "系统 产生了月度报告")
    """
    # 通知接收者
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name="接收者")
    
    # 动作发起者 (可以为空，例如系统通知)
    actor = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='actions', verbose_name="发起者")
    
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

    # 状态和时间戳
    unread = models.BooleanField(default=True, db_index=True, verbose_name="是否未读")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="时间戳")

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知中心"
        ordering = ['-timestamp']

    def __str__(self):
        if self.target:
            return f'{self.actor} {self.verb} {self.target}'
        return f'{self.actor} {self.verb}'

    def mark_as_read(self):
        if self.unread:
            self.unread = False
            self.save()

    def mark_as_unread(self):
        if not self.unread:
            self.unread = True
            self.save()

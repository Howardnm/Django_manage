from django.db import models


class ExternalMemberActivity(models.Model):
    """外部行为回流记录。
    """
    member_token = models.CharField("会员令牌", max_length=100, db_index=True)
    action = models.CharField("操作类型", max_length=50)
    target_name = models.CharField("目标牌号", max_length=100)
    timestamp = models.DateTimeField("发生时间")

    class Meta:
        verbose_name = "外部行为日志"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.member_token} - {self.action} - {self.target_name}"

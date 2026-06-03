from django.db import models


class MoldType(models.Model):
    """模具台账"""
    name = models.CharField("模具名称", max_length=100)
    mold_code = models.CharField("模具编号", max_length=50, unique=True)
    MOLD_TYPE_CHOICES = [
        ('TEST_SPECIMEN', '测试样条'),
        ('FINISHED_PART', '成品制件'),
        ('PROTOTYPE', '手板模型'),
        ('TOOLING', '治具/工装'),
        ('OTHER', '其他'),
    ]
    mold_type = models.CharField("模具类型", max_length=20, choices=MOLD_TYPE_CHOICES, default='TEST_SPECIMEN')
    standard = models.CharField("测试标准", max_length=20,
        choices=[('ISO', 'ISO'), ('ASTM', 'ASTM'), ('GB', 'GB'), ('OTHER', '其他')],
        default='ISO')
    specimen_description = models.TextField("样条描述", blank=True,
        help_text="如：ISO 527-2 1A 哑铃型拉伸样条")
    cavity_count = models.PositiveIntegerField("穴数", default=1)
    STATUS_CHOICES = [
        ('AVAILABLE', '可用'),
        ('MAINTENANCE', '维护中'),
        ('RETIRED', '已报废'),
    ]
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    description = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "模具台账"
        verbose_name_plural = "模具台账"
        ordering = ['mold_code']

    def __str__(self):
        return f"[{self.mold_code}] {self.name}"

from django.db import models


class SampleSplit(models.Model):
    """样品分拨"""
    DESTINATION_CHOICES = [
        ('SAMPLE_INVENTORY', '样品库(寄客户)'),
        ('INJECTION_MOLDING', '注塑房(内部测试)'),
        ('RETAINED', '留样'),
        ('WASTE', '废料'),
    ]
    production_order = models.ForeignKey(
        'app_trial_production.ProductionOrder', on_delete=models.CASCADE,
        related_name='sample_splits', verbose_name="关联工单")
    formula = models.ForeignKey(
        'app_formula.LabFormula', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="对应配方版本")
    destination = models.CharField("目的", max_length=30, choices=DESTINATION_CHOICES)
    quantity = models.DecimalField("数量(kg)", max_digits=10, decimal_places=2)
    packaging_desc = models.CharField("包装说明", max_length=100, blank=True)
    customer_destination = models.TextField("客户信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "样品分拨"
        verbose_name_plural = "样品分拨"
        ordering = ['created_at']


class SampleInventory(models.Model):
    """样品库存"""
    STATUS_CHOICES = [
        ('IN_STOCK', '在库'),
        ('SHIPPED', '已寄出'),
        ('USED', '已消耗'),
    ]
    sample_split = models.OneToOneField(
        SampleSplit, on_delete=models.CASCADE,
        related_name='inventory', verbose_name="来源分拨")
    production_order = models.ForeignKey(
        'app_trial_production.ProductionOrder', on_delete=models.CASCADE,
        related_name='sample_inventories', verbose_name="关联工单")
    quantity = models.DecimalField("数量(kg)", max_digits=10, decimal_places=2)
    status = models.CharField("库存状态", max_length=20, choices=STATUS_CHOICES, default='IN_STOCK')
    storage_location = models.CharField("存放位置", max_length=100, blank=True)
    customer_name = models.CharField("客户名称", max_length=100, blank=True)
    shipping_date = models.DateField("寄出日期", null=True, blank=True)
    tracking_number = models.CharField("物流单号", max_length=100, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "样品库存"
        verbose_name_plural = "样品库存"
        ordering = ['-created_at']

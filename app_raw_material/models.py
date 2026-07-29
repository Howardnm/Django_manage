from datetime import date, timedelta

from django.db import models
from django.db.models import Avg

from app_material.models import MaterialType, TestConfig



# 0. 均价计算配置 (Singleton)
class PriceAvgConfig(models.Model):
    """全局配置：均价计算月数，仅允许一条记录"""
    months = models.PositiveIntegerField(
        "均价计算月数", default=6,
        help_text="计算近N个月的均价（如 6=近半年，12=近一年）"
    )

    class Meta:
        verbose_name = "均价配置"
        verbose_name_plural = "均价配置"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"近{self.months}个月均价"


# 2. 原材料类型 (如：树脂、填充、助剂)
class RawMaterialType(models.Model):
    name = models.CharField("类型名称", max_length=50, unique=True)
    code = models.CharField("类型代码", max_length=20, blank=True, help_text="如：RESIN, FILLER")
    # 【新增】排序权重
    order = models.PositiveIntegerField("排序权重", default=0, help_text="数字越小越靠前 (例如: 树脂=1, 填充=2, 助剂=3)")
    # 【新增】描述字段
    description = models.TextField("描述", blank=True, help_text="类型说明或备注")
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "原材料类型"
        verbose_name_plural = "原材料类型库"
        ordering = ['order', 'name'] # 默认按权重排序


# 1. 供应商库
class Supplier(models.Model):
    name = models.CharField("供应商名称", max_length=100, unique=True)
    
    # 【修改】关联原材料类型 (多对多)
    product_categories = models.ManyToManyField(RawMaterialType, blank=True, verbose_name="主营产品种类", related_name="suppliers")
    
    # 销售联系人
    sales_contact = models.CharField("销售联系人", max_length=50, blank=True)
    sales_phone = models.CharField("销售手机", max_length=20, blank=True)
    
    # 技术联系人
    tech_contact = models.CharField("技术联系人", max_length=50, blank=True)
    tech_phone = models.CharField("技术手机", max_length=20, blank=True)
    
    description = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "供应商"
        verbose_name_plural = "供应商库"


# 3. 原材料主表
class RawMaterial(models.Model):
    # 关键修改：移除了 name 字段的 unique=True
    name = models.CharField("原材料名称", max_length=100, help_text="如：PA66")
    model_name = models.CharField("原材料型号", max_length=100, blank=True, help_text="如：2600, 101L")
    warehouse_code = models.CharField("内部物料编码", max_length=50, blank=True, unique=True, null=True, help_text="ERP/WMS编码")
    
    category = models.ForeignKey(RawMaterialType, on_delete=models.PROTECT, verbose_name="所属类型")
    
    # 【新增】适用材料类型 (多对多)
    # 用于标识该原材料适用于哪些基材体系 (例如：玻纤适用于 PA66, PBT, PP 等)
    suitable_materials = models.ManyToManyField(MaterialType, blank=True, verbose_name="适用材料体系", related_name="raw_materials")
    
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="供应商")
    
    usage_method = models.TextField("使用方法/描述", blank=True, help_text="如：需烘干，建议添加量...")
    
    _latest_price = models.DecimalField(
        "最新单价 (元/kg)", max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    _avg_price = models.DecimalField(
        "均价 (元/kg)", max_digits=10, decimal_places=2,
        null=True, blank=True
    )
    
    # 【新增】购入日期
    purchase_date = models.DateField("购入日期", null=True, blank=True)

    # 【新增】创建时间 (用于排序和筛选)
    created_at = models.DateTimeField("录入时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    def __str__(self):
        # 显示名称+型号
        full_name = f"{self.name}"
        if self.model_name:
            full_name += f" {self.model_name}"
        return f"{full_name} ({self.category.name})"

    @property
    def latest_price(self):
        """最新单价 — 取价格记录中最新日期的价格，无记录时返回存储值"""
        if self.pk is None:
            return self._latest_price
        latest = self.price_records.order_by('-date').first()
        return latest.price if latest else self._latest_price

    @latest_price.setter
    def latest_price(self, value):
        self._latest_price = value

    @property
    def avg_price(self):
        """近N月均价 — 时间范围内无记录时，回退到最新单价"""
        if self.pk is None:
            return self._avg_price
        config = PriceAvgConfig.get()
        cutoff = date.today() - timedelta(days=config.months * 30)
        records = self.price_records.filter(date__gte=cutoff)
        if records.exists():
            return records.aggregate(avg=Avg('price'))['avg']
        # 窗口内无记录时，回退到最新单价
        return self.latest_price

    @avg_price.setter
    def avg_price(self, value):
        self._avg_price = value

    class Meta:
        verbose_name = "原材料"
        verbose_name_plural = "原材料库"
        ordering = ['category', 'name']


# 4. 【新增】原材料性能指标子表
class RawMaterialProperty(models.Model):
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, related_name='properties')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    
    # 【修改】改为 DecimalField，保留3位小数
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)
    
    # 【新增】文本型数据 (用于存储非数字结果，如阻燃等级 V-0)
    value_text = models.CharField("文本结果", max_length=50, blank=True)
    
    # 【新增】测试日期
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)

    class Meta:
        verbose_name = "原材料性能"
        verbose_name_plural = "原材料性能表"
        # 【核心优化】添加联合索引或单列索引
        indexes = [
            models.Index(fields=['raw_material']),
            models.Index(fields=['test_config']),
            models.Index(fields=['value_text']),
        ]
        unique_together = ('raw_material', 'test_config')  # 防止重复录入同一指标
        ordering = ['test_config__category__order', 'test_config__order']


# 5. 价格历史记录
class RawMaterialPriceRecord(models.Model):
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE,
        related_name='price_records', verbose_name="原材料"
    )
    price = models.DecimalField("价格 (元/kg)", max_digits=10, decimal_places=2)
    date = models.DateField("日期")
    source = models.CharField(
        "来源/备注", max_length=200, blank=True,
        help_text="如：供应商报价、合同编号、市场询价等"
    )
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    class Meta:
        verbose_name = "价格历史记录"
        verbose_name_plural = "价格历史记录"
        ordering = ['-date']
        unique_together = ('raw_material', 'date')
        indexes = [
            models.Index(fields=['raw_material', '-date']),
        ]

    def __str__(self):
        return f"{self.raw_material} - ¥{self.price} ({self.date})"

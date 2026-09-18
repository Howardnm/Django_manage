import uuid

from django.db import models

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
    
    # 价格不落库：最新单价与近N月均价都从 RawMaterialPriceRecord 实时算出，
    # 口径的唯一实现在 services/price_service.py。
    # （历史上这里有 _latest_price / _avg_price 两个反规范化缓存列，
    #   需要靠信号级联维护，与实时值长期不自洽，已删除。）

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
        """最新单价 — 全库最新日期上、全部工厂报价的均价，保留 2 位小数。

        口径的唯一实现在 app_raw_material/services/price_service.py；
        这里只是薄委托，勿在此重新实现聚合（历史上多份拷贝已经漂移过）。
        未保存的实例或查不到任何报价 → None。
        """
        if self.pk is None:
            return None
        from app_raw_material.services import RawMaterialPriceService
        return RawMaterialPriceService.latest_price(self)

    @property
    def avg_price(self):
        """近N月均价 — 窗口内先按日均值、再对日均值求平均，保留 2 位小数。"""
        if self.pk is None:
            return None
        from app_raw_material.services import RawMaterialPriceService
        return RawMaterialPriceService.avg_price(self)

    @classmethod
    def annotate_latest_price(cls, queryset):
        """给 queryset 附上 `latest_price_sort` 排序表达式。

        **只用于 ORDER BY**：分页列表没法在 Python 侧排序，所以「最新单价」
        这一条口径不得不用 SQL 再表达一次（取最大日期 → 该日期各工厂报价的均价）。

        这是 services/price_service.py 里 `latest_from_series` 的 SQL 镜像 ——
        改价格口径时**两处都要改**。展示用的价格一律走 price_service，不要读这个注解。
        """
        from django.db.models import Avg, Max, OuterRef, Subquery

        # 内层必须切片：Django 的 exact lookup 要求子查询 has_limit_one()
        latest_date = (
            RawMaterialPriceRecord.objects
            .filter(raw_material=OuterRef('pk'))
            .values('raw_material')
            .annotate(d=Max('date'))
            .values('d')[:1]
        )
        latest_day_avg = (
            RawMaterialPriceRecord.objects
            .filter(raw_material=OuterRef('pk'), date=Subquery(latest_date))
            .values('raw_material')
            .annotate(a=Avg('price'))
            .values('a')
        )
        return queryset.annotate(latest_price_sort=Subquery(latest_day_avg))

    # ── 工厂级别方法 ──

    def latest_price_for_plant(self, plant):
        """指定工厂的最新单价（该工厂当日报价的均价），保留 2 位小数。

        口径统一说明：旧实现取 `order_by('-date').first()` 的单条记录，
        与非工厂版（当日跨工厂均价）不一致；现改为同一算法。
        """
        from app_raw_material.services import RawMaterialPriceService
        return RawMaterialPriceService.latest_price_for_plant(self, plant)

    def avg_price_for_plant(self, plant):
        """指定工厂的近N月均价（窗口内先日均、再对日均求均值），保留 2 位小数。

        口径统一说明：旧实现在窗口内直接做记录级 Avg，与非工厂版的
        「日均值的均值」不一致；现改为同一算法。
        """
        from app_raw_material.services import RawMaterialPriceService
        return RawMaterialPriceService.avg_price_for_plant(self, plant)

    @property
    def plants_with_prices(self):
        """返回有价格记录的工厂 QuerySet"""
        return Plant.objects.filter(
            pk__in=self.price_records.values('plant').distinct()
        )

    # ── 库存方法 ──

    def stock_for_plant(self, plant):
        """指定工厂的最新库存快照 QuerySet（按库位+批次分组）"""
        latest = self.stock_snapshots.filter(plant=plant).order_by('-synced_at').first()
        if latest is None:
            return self.stock_snapshots.none()
        return self.stock_snapshots.filter(
            plant=plant, sync_batch_id=latest.sync_batch_id
        )

    def stock_total_for_plant(self, plant):
        """指定工厂的非限制库存汇总（CLABS 合计）"""
        result = self.stock_for_plant(plant).aggregate(
            total=models.Sum('unrestricted_stock')
        )['total']
        return result or 0

    def stock_safety_for_plant(self, plant):
        """指定工厂的安全库存汇总（EISBE 合计）"""
        result = self.stock_for_plant(plant).aggregate(
            total=models.Sum('safety_stock')
        )['total']
        return result or 0

    def stock_available_above_safety(self, plant):
        """超额可用量 = CLABS合计 - EISBE合计。正数=安全，负数=低于安全线"""
        return self.stock_total_for_plant(plant) - self.stock_safety_for_plant(plant)

    @property
    def plants_with_stock(self):
        """返回有库存记录的工厂 QuerySet"""
        return Plant.objects.filter(
            pk__in=self.stock_snapshots.values('plant').distinct()
        )

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

    # 【新增】允许范围：字段定义对齐成品材料库 MaterialDataPoint，
    # 两边共用同一张 TestConfig，行为必须一致
    min_value = models.DecimalField("最小值", max_digits=10, decimal_places=3, null=True, blank=True,
                                    help_text="允许范围下限（含），数值类型使用")
    max_value = models.DecimalField("最大值", max_digits=10, decimal_places=3, null=True, blank=True,
                                    help_text="允许范围上限（含），数值类型使用")
    min_value_text = models.CharField("最小值(文本)", max_length=50, blank=True,
                                      help_text="文本/选择类型的最小值")
    max_value_text = models.CharField("最大值(文本)", max_length=50, blank=True,
                                      help_text="文本/选择类型的最大值")

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


# 5. 工厂 (Plant)
class Plant(models.Model):
    """工厂/评估范围 (对应 SAP BWKEY)"""
    code = models.CharField("工厂代码", max_length=20, unique=True,
                            help_text="SAP 评估范围代码，如 3011")
    name = models.CharField("工厂名称", max_length=100, blank=True,
                            help_text="如：上海工厂、昆山工厂")
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    class Meta:
        verbose_name = "工厂"
        verbose_name_plural = "工厂库"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} ({self.name})" if self.name else self.code


# 6. 价格历史记录
class RawMaterialPriceRecord(models.Model):
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE,
        related_name='price_records', verbose_name="原材料"
    )
    plant = models.ForeignKey(
        Plant, on_delete=models.PROTECT,
        verbose_name="工厂", help_text="该价格对应的工厂/评估范围"
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
        unique_together = ('raw_material', 'plant', 'date')
        indexes = [
            models.Index(fields=['raw_material', 'plant', '-date']),
        ]

    def __str__(self):
        plant_str = f" [{self.plant.code}]" if self.plant_id else ""
        return f"{self.raw_material}{plant_str} - ¥{self.price} ({self.date})"


# 7. 原材料库存快照
class RawMaterialStockSnapshot(models.Model):
    """原材料库存快照（SAP ZRFC_GET_MAT_STOCK）。

    同步按 (物料, 工厂) 比对签名：库存未变化只刷新 synced_at，
    变化才插入新 sync_batch_id。全量 RFC 不返回的零库存物料会补一行 0。
    过期非当前批次按命令 --keep-days 清理，当前批次始终保留。
    """

    sync_batch_id = models.UUIDField(
        "同步批次", default=uuid.uuid4, editable=False,
        help_text="同一次同步任务共享同一批次ID"
    )
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE,
        related_name='stock_snapshots', verbose_name="原材料"
    )
    plant = models.ForeignKey(
        Plant, on_delete=models.PROTECT,
        verbose_name="工厂", help_text="库存所在工厂 (SAP WERKS)"
    )
    storage_location = models.CharField(
        "库存地点", max_length=4, blank=True,
        help_text="SAP 库存地点代码 (LGORT)"
    )
    batch = models.CharField(
        "批号", max_length=10, blank=True, default="",
        help_text="批次号 (CHARG)，无批次时为空"
    )
    unrestricted_stock = models.DecimalField(
        "非限制库存", max_digits=13, decimal_places=3, default=0,
        help_text="实际可用库存量 (CLABS/LABST)，可直接用于生产领料"
    )
    safety_stock = models.DecimalField(
        "安全库存", max_digits=13, decimal_places=3, default=0,
        help_text="安全库存阈值 (EISBE)，MRP 参数，低于此值触发补货建议。非实际库存"
    )
    synced_at = models.DateTimeField(
        "同步时间", auto_now_add=True,
        help_text="该条记录写入数据库的时间"
    )

    @property
    def available_above_safety(self):
        """该行超额可用量 = CLABS - EISBE"""
        return self.unrestricted_stock - self.safety_stock

    @property
    def is_below_safety(self):
        """该行是否低于安全库存"""
        return self.available_above_safety < 0

    class Meta:
        verbose_name = "原材料库存快照"
        verbose_name_plural = "原材料库存快照"
        ordering = ['-synced_at', 'raw_material', 'plant']
        indexes = [
            models.Index(fields=['raw_material', 'plant', '-synced_at']),
            models.Index(fields=['sync_batch_id']),
            models.Index(fields=['synced_at']),
        ]

    def __str__(self):
        plant_str = f" [{self.plant.code}]" if self.plant_id else ""
        loc_str = f" / {self.storage_location}" if self.storage_location else ""
        return f"{self.raw_material}{plant_str}{loc_str} - CLABS={self.unrestricted_stock}"

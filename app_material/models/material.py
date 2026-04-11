import os
from django.db import models
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size
from collections import defaultdict

# ==========================================
# 1. 材料类型库
# ==========================================
class MaterialType(models.Model):
    CLASSIFICATION_CHOICES = [
        ('COMMODITY', '通用塑料 (PP, PE, PVC...)'),
        ('ENGINEERING', '工程塑料 (PA, PC, POM...)'),
        ('SPECIAL', '特种工程塑料 (PEEK, LCP, PPS...)'),
        ('FLUORINE', '氟塑料 (PTFE, PVDF...)'),
        ('ELASTOMER', '热塑性弹性体 (TPE, TPU...)'),
        ('BIO', '生物降解塑料 (PLA, PBAT...)'),
        ('ALLOY', '塑料合金 (PC/ABS...)'),
        ('OTHER', '其他'),
    ]
    name = models.CharField("类型名称", max_length=50, unique=True)
    classification = models.CharField("塑料归类", max_length=20, choices=CLASSIFICATION_CHOICES, default='ENGINEERING')
    description = models.TextField("描述", blank=True)

    def __str__(self): return self.name
    class Meta:
        verbose_name = "材料类型"
        verbose_name_plural = "材料类型库"

# ==========================================
# 2. 应用场景库
# ==========================================
class ApplicationScenario(models.Model):
    name = models.CharField("场景名称", max_length=100, unique=True)
    requirements = models.TextField("场景技术要求", blank=True)
    def __str__(self): return self.name
    class Meta:
        verbose_name = "应用场景"
        verbose_name_plural = "应用场景库"

# ==========================================
# 3. 指标分类
# ==========================================
class MetricCategory(models.Model):
    name = models.CharField("分类名称", max_length=50)
    order = models.PositiveIntegerField("排序权重", default=0)
    def __str__(self): return self.name
    class Meta:
        ordering = ['order']
        verbose_name = "指标分类"

# ==========================================
# 4. 测试配置项
# ==========================================
class TestConfig(models.Model):
    category = models.ForeignKey(MetricCategory, on_delete=models.CASCADE, verbose_name="所属分类")
    name = models.CharField("指标名称", max_length=100)
    standard = models.CharField("测试标准", max_length=50)
    condition = models.CharField("测试条件", max_length=50, blank=True)
    unit = models.CharField("单位", max_length=20, blank=True)
    order = models.PositiveIntegerField("排序权重", default=0)
    DATA_TYPE_CHOICES = [('NUMBER', '数值 (Number)'), ('TEXT', '文本 (Text)'), ('SELECT', '选择 (Select)')]
    data_type = models.CharField("数据类型", max_length=20, choices=DATA_TYPE_CHOICES, default='NUMBER')
    options_config = models.TextField("选项配置", blank=True)

    def __str__(self):
        cond_str = f" ({self.condition})" if self.condition else ""
        return f"[{self.category.name}] {self.name} - {self.standard}{cond_str}"

    def get_options_list(self):
        if not self.options_config: return []
        return [opt.strip() for opt in self.options_config.split(',') if opt.strip()]

    class Meta:
        verbose_name = "测试配置项"
        ordering = ['category__order', 'order']

# ==========================================
# 5. 材料主表 (Material Library)
# ==========================================
class MaterialLibrary(models.Model):
    grade_name = models.CharField("材料牌号", max_length=100, unique=True)
    manufacturer = models.CharField("生产厂家", max_length=100, blank=True)
    category = models.ForeignKey(MaterialType, on_delete=models.PROTECT, verbose_name="所属类型")
    scenarios = models.ManyToManyField(ApplicationScenario, blank=True, verbose_name="适用场景", related_name="materials")
    flammability = models.CharField("阻燃等级", max_length=20, blank=True,
                                    choices=[('HB', 'HB'), ('V-2', 'V-2'), ('V-0', 'V-0'), ('5VB', '5VB'), ('5VA', '5VA')])
    description = models.TextField("特性描述", blank=True)
    file_tds = models.FileField("TDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_msds = models.FileField("MSDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_rohs = models.FileField("RoHS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    def __str__(self): return f"{self.grade_name}"

    def get_grouped_properties(self):
        """核心业务逻辑：按分类分组获取性能数据，用于全系统展示"""
        grouped = defaultdict(list)
        points = self.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        for point in points:
            cat_name = point.test_config.category.name
            val = point.value_text if point.test_config.data_type != 'NUMBER' else point.value
            grouped[cat_name].append({
                'name': point.test_config.name,
                'value': val,
                'unit': point.test_config.unit,
                'standard': point.test_config.standard,
                'condition': point.test_config.condition,
                'data_type': point.test_config.data_type
            })
        result = []
        seen_cats = set()
        for point in points:
            cat_name = point.test_config.category.name
            if cat_name not in seen_cats:
                result.append({'category_name': cat_name, 'items': grouped[cat_name]})
                seen_cats.add(cat_name)
        return result

    class Meta:
        indexes = [models.Index(fields=['-created_at']), models.Index(fields=['category'])]
        ordering = ['-created_at']
        verbose_name = "材料库"

# ==========================================
# 6. 性能数据子表
# ==========================================
class MaterialDataPoint(models.Model):
    material = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='properties')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)
    value_text = models.CharField("文本结果", max_length=50, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)
    class Meta:
        verbose_name = "性能数据"
        unique_together = ('material', 'test_config')
        ordering = ['test_config__category__order', 'test_config__order']

# ==========================================
# 7. 额外附件子表
# ==========================================
class MaterialFile(models.Model):
    material = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='additional_files')
    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField(upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField(max_length=20, choices=[('UL', 'UL'), ('REACH', 'REACH'), ('COC', 'COC'), ('SPEC', 'SPEC')], default='OTHER')
    description = models.TextField("备注", blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.file:
            self.name = os.path.basename(self.file.name)
            self.__class__.objects.filter(pk=self.pk).update(name=self.name)

    def __str__(self): return f"{self.name} (V{self.version})"
    class Meta:
        verbose_name = "材料附件"
        ordering = ['-uploaded_at']

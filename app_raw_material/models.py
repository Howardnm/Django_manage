from django.db import models
from app_repository.models import TestConfig  # 引入测试标准库
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size  # 引入文件大小验证器


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
    name = models.CharField("原材料名称", max_length=100, unique=True, help_text="如：PA66")
    model_name = models.CharField("原材料型号", max_length=100, blank=True, help_text="如：2600, 101L")
    warehouse_code = models.CharField("内部物料编码", max_length=50, blank=True, unique=True, null=True, help_text="ERP/WMS编码")
    
    category = models.ForeignKey(RawMaterialType, on_delete=models.PROTECT, verbose_name="所属类型")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="供应商")
    
    usage_method = models.TextField("使用方法/描述", blank=True, help_text="如：需烘干，建议添加量...")
    
    cost_price = models.DecimalField("参考成本 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    
    # 【新增】购入日期
    purchase_date = models.DateField("购入日期", null=True, blank=True)

    # 【新增】核心文件
    file_tds = models.FileField("TDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_msds = models.FileField("MSDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_rohs = models.FileField("RoHS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    
    # 【新增】创建时间 (用于排序和筛选)
    created_at = models.DateTimeField("录入时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    def __str__(self):
        # 显示名称+型号
        full_name = f"{self.name}"
        if self.model_name:
            full_name += f" {self.model_name}"
        return f"{full_name} ({self.category.name})"

    class Meta:
        verbose_name = "原材料"
        verbose_name_plural = "原材料库"
        ordering = ['category', 'name']


# 4. 【新增】原材料性能指标子表
class RawMaterialProperty(models.Model):
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, related_name='properties')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    
    # 【修改】改为 DecimalField，保留3位小数
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3)
    
    # 【新增】测试日期
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)

    class Meta:
        verbose_name = "原材料性能"
        verbose_name_plural = "原材料性能表"
        unique_together = ('raw_material', 'test_config')  # 防止重复录入同一指标
        ordering = ['test_config__category__order', 'test_config__order']

import os

from django.db import models
from django.core.validators import FileExtensionValidator
from app_project.models import Project
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size  # 引入文件大小验证器


# ==============================================================================
# 板块一：公用基础库 (Common Library) - 核心资产，可复用
# ==============================================================================

class MaterialType(models.Model):
    """材料类型 (如: PA66, ABS, PC, PBT)"""
    # 行业术语建议使用 Classification (归类) 或 Family Group
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
    
    # 将字段名定为 classification，避免与 MaterialLibrary.category 混淆
    classification = models.CharField("塑料归类", max_length=20, choices=CLASSIFICATION_CHOICES, default='ENGINEERING')
    
    description = models.TextField("描述", blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "材料类型"
        verbose_name_plural = "材料类型库"


class ApplicationScenario(models.Model):
    """应用场景 (如: 汽车连接器, 手机外壳, 户外耐候件) - 用于未来场景选材"""
    name = models.CharField("场景名称", max_length=100, unique=True)
    requirements = models.TextField("场景技术要求", blank=True, help_text="如：耐高温等")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "应用场景"
        verbose_name_plural = "应用场景库"


# ==========================================
# 新增：主机厂 (OEM) 主数据
# ==========================================
class OEM(models.Model):
    """主机厂 (如：比亚迪、特斯拉、吉利)"""
    name = models.CharField("主机厂名称", max_length=100, unique=True)
    short_name = models.CharField("简称", max_length=20, blank=True)
    description = models.TextField("描述/备注", blank=True)

    def __str__(self):
        return self.short_name or self.name

    class Meta:
        verbose_name = "主机厂"
        verbose_name_plural = "主机厂库"


# ==========================================
# 新增：内部业务员主数据
# ==========================================
class Salesperson(models.Model):
    """我司销售/业务人员库"""
    name = models.CharField("姓名", max_length=50)
    phone = models.CharField("手机号", max_length=20, blank=True)
    email = models.EmailField("邮箱", blank=True)

    # 可选：关联系统账号 (如果业务员也是系统登录用户)
    # user = models.OneToOneField('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "业务员"
        verbose_name_plural = "业务员库"
        ordering = ['name']


# ==========================================
# 2. 性能指标配置体系 (Configuration)
# ==========================================
class MetricCategory(models.Model):
    """指标分类 (如: 物理性能, 机械性能)"""
    name = models.CharField("分类名称", max_length=50)
    order = models.PositiveIntegerField("排序权重", default=0)

    def __str__(self): return self.name

    class Meta:
        ordering = ['order']
        verbose_name = "指标分类"


class TestConfig(models.Model):
    """
    【核心配置】测试项目定义
    将 指标+标准+条件+单位 打包成一个选项
    """
    category = models.ForeignKey(MetricCategory, on_delete=models.CASCADE, verbose_name="所属分类")
    name = models.CharField("指标名称", max_length=100, help_text="如: 拉伸强度")
    standard = models.CharField("测试标准", max_length=50, help_text="如: ISO 527")
    condition = models.CharField("测试条件", max_length=50, blank=True, help_text="如: 50mm/min")
    unit = models.CharField("单位", max_length=20, blank=True)
    order = models.PositiveIntegerField("排序权重", default=0)
    
    # 【新增】数据类型字段
    DATA_TYPE_CHOICES = [
        ('NUMBER', '数值 (Number)'),
        ('TEXT', '文本 (Text)'),
        ('SELECT', '选择 (Select)'), # 预留，暂未完全实现动态选项配置
    ]
    data_type = models.CharField("数据类型", max_length=20, choices=DATA_TYPE_CHOICES, default='NUMBER', help_text="决定录入时的控件类型")
    
    # 【新增】选项配置 (仅当 data_type='SELECT' 时有效)
    # 格式: "V-0,V-1,V-2,HB" (逗号分隔)
    options_config = models.TextField("选项配置", blank=True, help_text="仅当类型为'选择'时有效，用逗号分隔选项，如: V-0,V-1,HB")

    def __str__(self):
        # 下拉框显示文本: [物理] 熔融指数 - ISO 1133 (230℃)
        cond_str = f" ({self.condition})" if self.condition else ""
        return f"[{self.category.name}] {self.name} - {self.standard}{cond_str}"
    
    def get_options_list(self):
        """解析选项配置为列表"""
        if not self.options_config:
            return []
        return [opt.strip() for opt in self.options_config.split(',') if opt.strip()]

    class Meta:
        verbose_name = "测试配置项"
        ordering = ['category__order', 'order']


# ==========================================
# 3. 材料主表 (Material Header)
# ==========================================
class MaterialLibrary(models.Model):
    grade_name = models.CharField("材料牌号", max_length=100, unique=True)
    manufacturer = models.CharField("生产厂家", max_length=100, blank=True)
    category = models.ForeignKey(MaterialType, on_delete=models.PROTECT, verbose_name="所属类型")

    # 多对多关联场景
    scenarios = models.ManyToManyField(ApplicationScenario, blank=True, verbose_name="适用场景", related_name="materials")

    # 基础属性
    flammability = models.CharField("阻燃等级", max_length=20, blank=True,
                                    choices=[('HB', 'HB'), ('V-2', 'V-2'), ('V-0', 'V-0'), ('5VB', '5VB'), ('5VA', '5VA')])
    description = models.TextField("特性描述", blank=True)

    # 核心文件
    file_tds = models.FileField("TDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_msds = models.FileField("MSDS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])
    file_rohs = models.FileField("RoHS", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])

    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    def __str__(self):
        return f"{self.grade_name}"

    # 【新增】辅助方法：将 EAV 数据转为字典，方便模板调用
    def get_properties_dict(self):
        """
        返回格式：
        {
            '密度': {'value': 1.2, 'unit': 'g/cm³'},
            '拉伸强度': {'value': 50, 'unit': 'MPa'},
            ...
        }
        """
        data = {}
        # 预加载 test_config 避免 N+1
        for point in self.properties.select_related('test_config').all():
            key = point.test_config.name
            # 兼容非数值类型
            val = point.value_text if point.test_config.data_type != 'NUMBER' else point.value
            
            data[key] = {
                'value': val,
                'unit': point.test_config.unit,
                'standard': point.test_config.standard,
                'condition': point.test_config.condition
            }
        return data

    # 【新增】辅助方法：按分类分组获取性能数据，用于详情页展示
    def get_grouped_properties(self):
        """
        返回格式：
        [
            {
                'category_name': '物理性能',
                'items': [
                    {'name': '密度', 'value': 1.2, 'unit': 'g/cm³', 'standard': 'ISO 1183', 'condition': ''},
                    ...
                ]
            },
            ...
        ]
        """
        from collections import defaultdict
        grouped = defaultdict(list)
        
        # 预加载 test_config 和 category
        points = self.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        
        for point in points:
            cat_name = point.test_config.category.name
            
            # 兼容非数值类型
            val = point.value_text if point.test_config.data_type != 'NUMBER' else point.value
            
            grouped[cat_name].append({
                'name': point.test_config.name,
                'value': val,
                'unit': point.test_config.unit,
                'standard': point.test_config.standard,
                'condition': point.test_config.condition,
                'remark': point.remark
            })
            
        # 转换为列表格式，保持分类顺序 (因为 defaultdict 是无序的，但我们查询时已经按 category__order 排序了)
        # 为了确保分类顺序正确，我们最好再处理一下，或者直接依赖查询顺序
        # 这里简单处理：按出现的顺序生成列表
        result = []
        seen_cats = set()
        # 重新遍历一遍以保持顺序 (虽然有点低效，但数据量很小)
        for point in points:
            cat_name = point.test_config.category.name
            if cat_name not in seen_cats:
                result.append({
                    'category_name': cat_name,
                    'items': grouped[cat_name]
                })
                seen_cats.add(cat_name)
                
        return result

    class Meta:
        # 【核心优化】添加联合索引或单列索引
        indexes = [
            # 1. 针对默认排序字段添加索引 (解决打开页面慢)
            models.Index(fields=['-created_at']),
            # 2. 针对高频筛选的外键添加索引 (解决筛选慢)
            models.Index(fields=['category']),
        ]
        ordering = ['-created_at']
        verbose_name = "材料库"


# ==========================================
# 4. 性能数据子表 (Data Lines)
# ==========================================
class MaterialDataPoint(models.Model):
    material = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='properties')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    
    # 数值型数据
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)
    
    # 【新增】文本型数据 (用于存储非数字结果，如阻燃等级 V-0)
    value_text = models.CharField("文本结果", max_length=50, blank=True)
    
    remark = models.CharField("备注", max_length=50, blank=True)

    class Meta:
        verbose_name = "性能数据"
        unique_together = ('material', 'test_config')  # 防止重复录入同一项
        ordering = ['test_config__category__order', 'test_config__order']


# ==========================================
# 5. 额外附件子表 (Attachments)
# ==========================================

FILE_TYPE_CHOICES = [
    ('UL', 'UL黄卡/认证'),
    ('REACH', 'REACH报告'),
    ('COC', 'COC/出厂报告'),
    ('SPEC', '详细规格书'),
    ('OTHER', '其他资料'),
]

class MaterialFile(models.Model):
    material = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='additional_files')
    file = models.FileField(upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='OTHER')
    description = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def filename(self):
        import os
        return os.path.basename(self.file.name)

    def __str__(self):
        return self.description or self.filename()

    class Meta:
        verbose_name = "材料附件"
        verbose_name_plural = "材料附件库"
        ordering = ['-uploaded_at']


# ==============================================================================
# 板块二：客户库 (CRM Lite) - 客户信息管理
# ==============================================================================

class Customer(models.Model):
    """客户基础信息"""
    company_name = models.CharField("公司全称", max_length=100, unique=True)
    short_name = models.CharField("简称", max_length=20, blank=True)
    address = models.CharField("地址", max_length=200, blank=True)

    # 主要联系人
    contact_name = models.CharField("商务联系人", max_length=50, blank=True)
    phone = models.CharField("手机", max_length=20, blank=True)
    email = models.EmailField("邮箱", blank=True)

    # 质量/技术对接人 (项目开发中很重要)
    tech_contact = models.CharField("技术/质量对接人", max_length=50, blank=True)
    tech_phone = models.CharField("技术联系电话", max_length=20, blank=True)

    def __str__(self):
        return self.short_name or self.company_name

    class Meta:
        verbose_name = "客户"
        verbose_name_plural = "客户库"


# ==============================================================================
# 板块三：项目档案 (Project Profile) - 连接器
# ==============================================================================

class ProjectRepository(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='repository', verbose_name="关联项目")

    # 1. 商业与基础信息
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="直接客户 (Tier1)")
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="终端主机厂 (OEM)")
    # 【新增】关联业务员
    salesperson = models.ForeignKey(Salesperson, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="项目业务员")
    # 2. 产品与材料
    product_name = models.CharField("客户产品名称", max_length=100, blank=True)
    product_code = models.CharField("产品代码/零件号", max_length=100, blank=True)
    material = models.ForeignKey('MaterialLibrary', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用材料")

    # 3. 成本与价格 (新增)
    competitor_price = models.DecimalField("竞品售价 (RMB/kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    target_cost = models.DecimalField("目标成本 (RMB/kg)", max_digits=10, decimal_places=2, null=True, blank=True)

    updated_at = models.DateTimeField("最后更新", auto_now=True)



    def __str__(self):
        return f"{self.project.name} 档案"

    class Meta:
        verbose_name = "项目档案"
        verbose_name_plural = "项目档案"
        # 【核心优化】添加联合索引或单列索引
        indexes = [
            # 1. 针对默认排序字段添加索引 (解决打开页面慢)
            models.Index(fields=['-updated_at']),

            # 2. 针对高频筛选的外键添加索引 (解决筛选慢)
            models.Index(fields=['project']),
            models.Index(fields=['customer']),
            models.Index(fields=['oem']),
            models.Index(fields=['salesperson']),
            models.Index(fields=['material']),
        ]
        ordering = ['-updated_at']


# ==========================================
# 新增：项目资料文件库 (多文件支持)
# ==========================================
class ProjectFile(models.Model):
    """
    项目专属文件库 (一对多)
    """
    FILE_TYPE_CHOICES = [
        ('DRAWING_2D', '2D图纸'),
        ('DRAWING_3D', '3D数模'),
        ('STANDARD', '技术标准'),
        ('REPORT', '检测/测试报告'),
        ('QUOTE', '报价/商务'),
        ('OTHER', '其他资料'),
    ]

    repository = models.ForeignKey(ProjectRepository, on_delete=models.CASCADE, related_name='files', verbose_name="所属档案")
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=FILE_TYPE_CHOICES, default='OTHER')
    description = models.CharField("文件说明", max_length=100, blank=True)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)

    def filename(self):
        return os.path.basename(self.file.name)

    def __str__(self):
        return self.description or self.filename()

    class Meta:
        verbose_name = "项目文件"
        verbose_name_plural = "项目文件库"
        # 【核心优化】添加联合索引或单列索引
        indexes = [
            # 1. 针对默认排序字段添加索引 (解决打开页面慢)
            models.Index(fields=['-uploaded_at']),
            # 2. 针对高频筛选的外键添加索引 (解决筛选慢)
            models.Index(fields=['repository']),
        ]
        ordering = ['-uploaded_at']

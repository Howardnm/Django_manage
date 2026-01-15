from django.db import models
from django.core.validators import FileExtensionValidator
from app_project.models import Project
from .utils.repo_file_path import repo_file_path  # 引入刚才写的路径函数


# ==============================================================================
# 板块一：公用基础库 (Common Library) - 核心资产，可复用
# ==============================================================================

class MaterialType(models.Model):
    """材料类型 (如: PA66, ABS, PC, PBT)"""
    name = models.CharField("类型名称", max_length=50, unique=True)
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


class MaterialLibrary(models.Model):
    """
    材料数据库 (具体的牌号)
    TDS/MSDS 是跟随材料走的，不管哪个项目用，文件都是同一份。
    """
    # --- 1. 基础信息 ---
    grade_name = models.CharField("材料牌号", max_length=100, unique=True, help_text="如: A3EG6")
    manufacturer = models.CharField("生产厂家", max_length=100, blank=True, help_text="如: BASF")
    # 关联到《材料类型models》
    category = models.ForeignKey(MaterialType, on_delete=models.PROTECT, verbose_name="所属类型")
    # 关联到《应用场景库》
    scenario = models.ForeignKey(ApplicationScenario, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="应用场景")

    # --- 2. 物理性能 (Physical Properties) ---
    density = models.FloatField("密度 (g/cm³)", blank=True, null=True)
    melt_index = models.FloatField("熔融指数 M.I (g/10min)", blank=True, null=True, help_text="测试标准通常为 ASTM D1238")
    ash_content = models.FloatField("灰分 Ash (%)", blank=True, null=True)
    shrinkage_md = models.FloatField("收缩率-MD (横向 %)", blank=True, null=True)
    shrinkage_td = models.FloatField("收缩率-TD (纵向 %)", blank=True, null=True)

    # --- 3. 机械性能 (Mechanical Properties) ---
    tensile_strength = models.FloatField("拉伸强度 (MPa)", blank=True, null=True)
    elongation_break = models.FloatField("断裂伸长率 EL (%)", blank=True, null=True)
    flexural_strength = models.FloatField("弯曲强度 FS (MPa)", blank=True, null=True)
    flexural_modulus = models.FloatField("弯曲模量 FM (MPa)", blank=True, null=True)
    izod_impact_23 = models.FloatField("Izod缺口冲击 23℃ (kJ/m²)", blank=True, null=True)
    izod_impact_minus_30 = models.FloatField("Izod缺口冲击 -30℃ (kJ/m²)", blank=True, null=True)

    # --- 4. 热学性能 (Thermal Properties) ---
    hdt_045 = models.FloatField("热变形温度 0.45MPa (℃)", blank=True, null=True)
    hdt_180 = models.FloatField("热变形温度 1.8MPa (℃)", blank=True, null=True)
    # 阻燃等级 (改为选择)
    FLAMMABILITY_CHOICES = [
        ('HB', 'HB'),
        ('V-2', 'V-2'),
        ('V-1', 'V-1'),
        ('V-0', 'V-0'),
        ('5VB', '5VB'),
        ('5VA', '5VA'),
    ]
    flammability = models.CharField("阻燃等级", max_length=10, choices=FLAMMABILITY_CHOICES, blank=True, null=True)

    # --- 5. 文件与描述 ---
    file_tds = models.FileField("TDS (物性表)", upload_to=repo_file_path, blank=True, null=True)
    file_msds = models.FileField("MSDS (化学品安全)", upload_to=repo_file_path, blank=True, null=True)
    file_rohs = models.FileField("RoHS/环保报告", upload_to=repo_file_path, blank=True, null=True)

    description = models.TextField("材料特性描述", blank=True, help_text="例如：高流动性、抗UV、玻纤增强等特性说明")

    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    def __str__(self):
        return f"{self.grade_name} ({self.manufacturer})"

    class Meta:
        verbose_name = "材料库"
        verbose_name_plural = "材料库"
        ordering = ['-created_at'] # 默认按创建时间倒序排列 (最新的在最前)


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
    """
    项目专属资料箱
    OneToOne 关联 Project，确保一个项目只有一个档案
    """
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='repository', verbose_name="关联项目")

    # 1. 引用基础数据 (指针)
        # 客户库 (CRM Lite) - 客户信息管理
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所属客户")
        # 材料库
    material = models.ForeignKey(MaterialLibrary, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用材料")

    # 2. 项目专属文件 (这些文件只属于这个项目，换个项目图纸就不一样了)
    product_name = models.CharField("客户产品名称", max_length=100, blank=True)
    product_code = models.CharField("产品代码/零件号", max_length=100, blank=True)

    file_drawing_2d = models.FileField("2D图纸 (PDF/DWG)", upload_to=repo_file_path, blank=True, null=True)
    file_drawing_3d = models.FileField(
        "3D图纸 (STEP/PRT)",
        upload_to=repo_file_path,
        blank=True, null=True,
        validators=[FileExtensionValidator(['stp', 'step', 'prt', 'igs', 'x_t', 'zip', '7z'])]
    )
    file_standard = models.FileField("产品技术标准书", upload_to=repo_file_path, blank=True, null=True)

    # 3. 项目专用报告
    file_inspection = models.FileField("专用检查/测试报告", upload_to=repo_file_path, blank=True, null=True)

    updated_at = models.DateTimeField("最后更新时间", auto_now=True)

    def __str__(self):
        return f"{self.project.name} - 资料档案"

    class Meta:
        verbose_name = "项目档案"
        verbose_name_plural = "项目档案"



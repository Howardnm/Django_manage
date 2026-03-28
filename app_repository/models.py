import os

from django.db import models

from app_project.models import Project, ProjectNode
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size
from django.contrib.auth.models import User


# ==========================================
# 新增：主机厂 (OEM) 主数据
# ==========================================
class OEM(models.Model):
    """主机厂 (如：比亚迪、特斯拉、吉利)"""
    LEVEL_CHOICES = [
        ('A', 'A级 (核心客户)'),
        ('B', 'B级 (重要客户)'),
        ('C', 'C级 (普通客户)'),
        ('D', 'D级 (潜在客户)'),
    ]

    name = models.CharField("主机厂名称", max_length=100, unique=True)
    short_name = models.CharField("简称", max_length=20, blank=True)
    description = models.TextField("描述/备注", blank=True)

    # --- 新增字段 ---
    website = models.URLField("官方网站", blank=True)
    contact_name = models.CharField("主要联系人", max_length=50, blank=True)
    contact_phone = models.CharField("联系电话", max_length=50, blank=True)
    contact_email = models.EmailField("电子邮箱", blank=True)
    address = models.CharField("公司地址", max_length=200, blank=True)
    cooperation_level = models.CharField("合作级别", max_length=10, choices=LEVEL_CHOICES, default='C')

    def __str__(self):
        return self.short_name or self.name

    class Meta:
        verbose_name = "主机厂"
        verbose_name_plural = "主机厂库"


# ==========================================
# 【新增】主机厂标准文件模型
# ==========================================
class OEMStandardFile(models.Model):
    """主机厂标准文件库"""
    FILE_TYPE_CHOICES = [
        ('MATERIAL', '材料标准'),
        ('TEST', '测试标准'),
        ('QUALITY', '质量协议'),
        ('OTHER', '其他标准'),
    ]

    oem = models.ForeignKey(OEM, on_delete=models.CASCADE, related_name='standard_files', verbose_name="所属主机厂")
    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=FILE_TYPE_CHOICES, default='MATERIAL')
    description = models.TextField("备注/详细说明", blank=True)
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="上传人")
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)

    # 版本管理字段
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # 核心逻辑：在文件保存后，提取经过清洗和冲突处理后的真实文件名并回填
        if is_new and self.file:
            self.name = os.path.basename(self.file.name)
            # 使用 update 避免触发信号和递归保存
            self.__class__.objects.filter(pk=self.pk).update(name=self.name)

    def __str__(self):
        return f"{self.name} (V{self.version})"

    class Meta:
        verbose_name = "主机厂标准文件"
        verbose_name_plural = "主机厂标准文件库"
        ordering = ['-uploaded_at']


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
    material = models.ForeignKey('app_material.MaterialLibrary', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用材料")

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

    # 【新增】关联进度节点 (可选)
    node = models.ForeignKey(ProjectNode, on_delete=models.SET_NULL, null=True, blank=True, related_name='files', verbose_name="关联节点")

    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=FILE_TYPE_CHOICES, default='OTHER')
    description = models.TextField("备注/详细说明", blank=True)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)

    # 版本管理字段
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # 核心逻辑：在文件保存后，提取真实的最终文件名回填到 name 字段
        if is_new and self.file:
            self.name = os.path.basename(self.file.name)
            self.__class__.objects.filter(pk=self.pk).update(name=self.name)

    def filename(self):
        return os.path.basename(self.file.name)

    def __str__(self):
        desc = self.name or self.filename()
        return f"{desc} (V{self.version})"

    class Meta:
        verbose_name = "项目文件"
        verbose_name_plural = "项目文件库"
        # 【核心优化】添加联合索引或单列索引
        indexes = [
            # 1. 针对默认排序字段添加索引 (解决打开页面慢)
            models.Index(fields=['-uploaded_at']),
            # 2. 针对高频筛选的外键添加索引 (解决筛选慢)
            models.Index(fields=['repository']),
            models.Index(fields=['node']),
        ]
        ordering = ['-uploaded_at']

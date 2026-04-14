from django.db import models

class CatalogCategory(models.Model):
    """手册分类：镜像材质系列 (如 PA66, PP)"""
    name = models.CharField("分类名称", max_length=50)
    remote_type_id = models.IntegerField("远程材料类型ID", null=True, blank=True, unique=True)
    icon = models.CharField("图标代码", max_length=50, blank=True, default='package')
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("是否启用", default=True)
    def __str__(self): return self.name
    class Meta:
        verbose_name = "材料类型"
        verbose_name_plural = "1.材料类型列表"
        ordering = ['order']

class MirrorScenario(models.Model):
    """本地镜像：应用场景"""
    name = models.CharField("场景名称", max_length=100)
    remote_id = models.IntegerField("远程ID", unique=True)
    def __str__(self): return self.name
    class Meta:
        verbose_name = "应用场景"
        verbose_name_plural = "2.应用场景列表"

class MirrorCharacteristic(models.Model):
    """本地镜像：材料特征"""
    name = models.CharField("特征名称", max_length=100)
    remote_id = models.IntegerField("远程ID", unique=True)
    def __str__(self): return self.name
    class Meta:
        verbose_name = "材料特征"
        verbose_name_plural = "3.材料特征列表"

class CatalogProduct(models.Model):
    """
    手册产品：镜像远程物料
    采用关系型镜像，确保 SQL 查询效率
    """
    remote_material_id = models.IntegerField("远程物料ID", unique=True)
    display_name = models.CharField("展示牌号", max_length=100)
    category = models.ForeignKey(CatalogCategory, on_delete=models.PROTECT, verbose_name="手册分类")
    
    # --- 结构化镜像关联 ---
    scenarios = models.ManyToManyField(MirrorScenario, blank=True, verbose_name="镜像场景")
    characteristics = models.ManyToManyField(MirrorCharacteristic, blank=True, verbose_name="镜像特征")
    
    # 存储基础描述，避免列表页调 API
    description = models.TextField("产品描述", blank=True)
    
    is_published = models.BooleanField("是否对外发布", default=False)
    is_featured = models.BooleanField("是否推荐", default=False)
    
    view_count = models.PositiveIntegerField("查看次数", default=0)
    download_count = models.PositiveIntegerField("下载次数", default=0)
    published_at = models.DateTimeField("发布时间", auto_now_add=True)

    def __str__(self): return self.display_name

    class Meta:
        verbose_name = "手册产品"
        verbose_name_plural = "4.手册产品列表"
        ordering = ['-published_at', '-id']

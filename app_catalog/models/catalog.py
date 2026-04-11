from django.db import models

class CatalogCategory(models.Model):
    """手册分类：镜像远程材质分类，支持本地展示自定义"""
    name = models.CharField("分类名称", max_length=50)
    remote_type_id = models.IntegerField("远程材料类型ID", null=True, blank=True, unique=True)
    icon = models.CharField("图标代码", max_length=50, blank=True, default='package', help_text="Tabler 图标名称，如 car, plug, phone")
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("是否启用", default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "手册分类"
        verbose_name_plural = "1.手册分类管理"
        ordering = ['order']

class CatalogProduct(models.Model):
    """手册产品：镜像远程物料，存储发布权限和访问统计"""
    remote_material_id = models.IntegerField("远程物料ID", unique=True)
    display_name = models.CharField("展示牌号", max_length=100)
    category = models.ForeignKey(CatalogCategory, on_delete=models.PROTECT, verbose_name="手册分类")
    
    is_published = models.BooleanField("是否对外发布", default=False)
    is_featured = models.BooleanField("是否推荐", default=False)
    
    view_count = models.PositiveIntegerField("查看次数", default=0)
    download_count = models.PositiveIntegerField("下载次数", default=0)
    published_at = models.DateTimeField("发布时间", auto_now_add=True)

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = "手册产品"
        verbose_name_plural = "2.手册产品列表"
        # 修正：添加默认排序，解决分页警告问题
        ordering = ['-published_at', '-id']

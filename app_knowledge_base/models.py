from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField, HnswIndex
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from common_utils.upload_file_path import upload_file_path


class Category(models.Model):
    """
    文献分类
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="分类名称")
    description = models.TextField(blank=True, null=True, verbose_name="分类描述")

    class Meta:
        verbose_name = "文献分类"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Tag(models.Model):
    """
    文献标签
    """
    name = models.CharField(max_length=50, unique=True, verbose_name="标签名称")

    class Meta:
        verbose_name = "文献标签"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Document(models.Model):
    """
    文献/知识库条目
    """
    class DocumentType(models.TextChoices):
        FILE = 'FILE', '文件'
        TEXT = 'TEXT', '纯文本'

    title = models.CharField(max_length=255, verbose_name="标题")
    description = models.TextField(blank=True, null=True, verbose_name="摘要/描述")
    
    original_file = models.FileField(upload_to=upload_file_path, blank=True, null=True, verbose_name="原始文件")
    
    content = models.TextField(blank=True, null=True, verbose_name="文本内容")
    
    embedding = VectorField(dimensions=768, blank=True, null=True, verbose_name="向量嵌入")
    
    document_type = models.CharField(max_length=10, choices=DocumentType.choices, default=DocumentType.TEXT, verbose_name="条目类型")
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="分类")
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="标签")
    
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="上传者")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "文献"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            HnswIndex(
                name='document_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_l2_ops']
            ),
            # 为文本内容字段创建GIN索引，以加速中文全文搜索。
            # 使用您已创建的名为 'chinese' 的文本搜索配置。
            GinIndex(
                SearchVector('content', config='chinese'),
                name='document_content_gin_idx',
            ),
        ]

    def __str__(self):
        return self.title

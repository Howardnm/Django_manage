from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField, HnswIndex
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from common_utils.upload_file_path import upload_file_path


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="分类名称")
    description = models.TextField(blank=True, null=True, verbose_name="分类描述")
    class Meta:
        verbose_name = "文献分类"
        verbose_name_plural = verbose_name
    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="标签名称")
    class Meta:
        verbose_name = "文献标签"
        verbose_name_plural = verbose_name
    def __str__(self):
        return self.name


class Document(models.Model):
    class DocumentType(models.TextChoices):
        FILE = 'FILE', '文件'
        TEXT = 'TEXT', '纯文本'

    class ProcessingStatus(models.TextChoices):
        PENDING = 'PENDING', '待处理'
        PROCESSING = 'PROCESSING', '处理中'
        SUCCESS = 'SUCCESS', '处理成功'
        FAILED = 'FAILED', '处理失败'

    title = models.CharField(max_length=255, verbose_name="标题")
    description = models.TextField(blank=True, null=True, verbose_name="摘要/描述")
    original_file = models.FileField(upload_to=upload_file_path, blank=True, null=True, verbose_name="原始文件")
    embedding = VectorField(dimensions=768, blank=True, null=True, verbose_name="向量嵌入")
    document_type = models.CharField(max_length=10, choices=DocumentType.choices, default=DocumentType.TEXT, verbose_name="条目类型")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="分类")
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="标签")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="上传者")
    author = models.CharField(max_length=255, blank=True, null=True, verbose_name="作者")
    published_at = models.DateField(blank=True, null=True, verbose_name="发布日期", db_index=True)
    source = models.CharField(max_length=255, blank=True, null=True, verbose_name="来源/期刊")
    page_count = models.PositiveIntegerField(blank=True, null=True, verbose_name="页数")
    file_size = models.BigIntegerField(blank=True, null=True, verbose_name="文件大小(bytes)")
    mime_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="MIME类型")
    processing_status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING, verbose_name="处理状态", db_index=True)
    processing_error = models.TextField(blank=True, null=True, verbose_name="处理错误信息")
    processed_at = models.DateTimeField(blank=True, null=True, verbose_name="上次处理时间")
    related_documents = models.ManyToManyField('self', blank=True, verbose_name="相关文献")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        verbose_name = "文献"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            HnswIndex(name='doc_embedding_hnsw_idx', fields=['embedding'], m=16, ef_construction=64, opclasses=['vector_l2_ops']),
            GinIndex(fields=['search_vector'], name='doc_search_vector_idx'),
        ]

    def __str__(self):
        return self.title

    def update_search_vector(self):
        """计算并更新搜索向量"""
        content_text = ''
        # 检查 content_model 是否存在且已加载
        if hasattr(self, 'content_model') and self.content_model:
            content_text = self.content_model.content or ''
        
        vector = (
            SearchVector('title', weight='A', config='chinese') +
            SearchVector('author', weight='B', config='chinese') +
            SearchVector('source', weight='B', config='chinese') +
            SearchVector(models.Value(content_text), weight='D', config='chinese')
        )
        # 使用 .update() 避免触发 save() 导致无限递归
        Document.objects.filter(pk=self.pk).update(search_vector=vector)

    def save(self, *args, **kwargs):
        # 关键修改：重写 save 方法
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # 如果是新创建的对象，或者有关联的 content，则更新向量
        # 避免在 content 还不存在时执行
        if not is_new or hasattr(self, 'content_model'):
             self.update_search_vector()


class DocumentContent(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, primary_key=True, related_name='content_model')
    content = models.TextField(blank=True, null=True, verbose_name="提取的文本内容")

    def __str__(self):
        return f"Content for: {self.document.title}"

    def save(self, *args, **kwargs):
        # 关键修改：保存自己，然后调用关联 document 的 save 方法
        super().save(*args, **kwargs)
        self.document.save()

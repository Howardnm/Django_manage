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
    
    # --- 新增：为AI Agent准备的字段 ---
    structured_data = models.JSONField(blank=True, null=True, verbose_name="AI提取的结构化数据")
    
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
        content_text = ''
        if hasattr(self, 'content_model') and self.content_model:
            content_text = self.content_model.content or ''
        
        vector = (
            SearchVector('title', weight='A', config='chinese') +
            SearchVector('author', weight='B', config='chinese') +
            SearchVector('source', weight='B', config='chinese') +
            SearchVector(models.Value(content_text), weight='D', config='chinese')
        )
        Document.objects.filter(pk=self.pk).update(search_vector=vector)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if not is_new or hasattr(self, 'content_model'):
             self.update_search_vector()


class DocumentContent(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, primary_key=True, related_name='content_model')
    content = models.TextField(blank=True, null=True, verbose_name="提取的文本内容")

    def __str__(self):
        return f"Content for: {self.document.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.document.save()


# --- 新增：AI Agent相关模型 ---

class AgentTask(models.Model):
    """
    AI Agent 任务队列
    """
    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', '待处理'
        PROCESSING = 'PROCESSING', '处理中'
        SUCCESS = 'SUCCESS', '成功'
        FAILED = 'FAILED', '失败'

    class TaskType(models.TextChoices):
        SUMMARIZE = 'SUMMARIZE', '生成摘要'
        EXTRACT_KEYWORDS = 'EXTRACT_KEYWORDS', '提取关键词'
        EXTRACT_STRUCTURED_DATA = 'EXTRACT_STRUCTURED_DATA', '提取结构化数据'
        # ...可以根据需要添加更多任务类型

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='agent_tasks', verbose_name="关联文献")
    task_type = models.CharField(max_length=50, choices=TaskType.choices, verbose_name="任务类型")
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True, verbose_name="任务状态")
    
    input_params = models.JSONField(blank=True, null=True, verbose_name="输入参数")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="完成时间")

    class Meta:
        verbose_name = "AI Agent 任务"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']


class AgentActionLog(models.Model):
    """
    AI Agent 行为日志，用于审计和追踪
    """
    class ActionStatus(models.TextChoices):
        SUCCESS = 'SUCCESS', '成功'
        FAILED = 'FAILED', '失败'

    task = models.ForeignKey(AgentTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='action_logs', verbose_name="关联任务")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='action_logs', verbose_name="关联文献")
    
    agent_name = models.CharField(max_length=100, verbose_name="Agent名称")
    action_type = models.CharField(max_length=100, verbose_name="操作类型") # e.g., 'llm_call', 'db_query'
    
    prompt = models.TextField(blank=True, null=True, verbose_name="输入/Prompt")
    result = models.TextField(blank=True, null=True, verbose_name="输出/Result")
    
    status = models.CharField(max_length=20, choices=ActionStatus.choices, verbose_name="状态")
    error_message = models.TextField(blank=True, null=True, verbose_name="错误信息")
    
    duration_ms = models.PositiveIntegerField(blank=True, null=True, verbose_name="耗时(毫秒)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        verbose_name = "AI Agent 行为日志"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

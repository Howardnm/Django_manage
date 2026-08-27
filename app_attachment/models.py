"""
统一附件模型

通过 GenericForeignKey 支持任意业务模型作为父对象，
替换项目中原有的分散附件子表和内联 FileField。
"""
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .storage import upload_file_path
from .validators import validate_file_size


class Attachment(models.Model):
    """
    统一附件模型。

    使用 GFK (GenericForeignKey) 关联任意父对象，
    支持 MaterialLibrary、ResearchProject、ProjectRepository、
    OEM、RawMaterial、LabFormula、ScrewCombination 等所有业务模型。
    """

    # ---- GenericForeignKey: 关联任意父对象 ----
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='父对象类型',
        db_index=True,
    )
    object_id = models.PositiveIntegerField(
        verbose_name='父对象ID',
        db_index=True,
    )
    parent = GenericForeignKey('content_type', 'object_id')

    # ---- 核心文件字段 ----
    file = models.FileField(
        '文件附件',
        upload_to=upload_file_path,
        validators=[validate_file_size],
    )
    display_name = models.CharField(
        '显示名称',
        max_length=200,
        blank=True,
        help_text='留空则自动使用文件名',
    )
    description = models.TextField('备注/描述', blank=True)

    # ---- 分类与版本 ----
    category = models.CharField(
        '文件分类',
        max_length=30,
        blank=True,
        db_index=True,
        help_text='如: TDS, MSDS, RoHS, REPORT, DRAWING, OTHER',
    )
    group_key = models.CharField(
        '分组标识',
        max_length=100,
        blank=True,
        db_index=True,
        help_text='通用分组键，如"node:15"表示关联项目节点15，留空则为通用资料',
    )
    version = models.PositiveIntegerField('版本号', default=1)

    # ---- 审计字段 ----
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='上传人',
    )
    uploaded_at = models.DateTimeField('上传时间', auto_now_add=True, db_index=True)
    file_size = models.BigIntegerField('文件大小(Bytes)', default=0, editable=False)

    # ---- 安全令牌 ----
    download_token = models.UUIDField(
        '下载令牌',
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text='下载 URL 中的唯一令牌，防止 ID 枚举',
    )

    # ---- 软删除 ----
    is_deleted = models.BooleanField('已删除', default=False, db_index=True)

    class Meta:
        verbose_name = '附件'
        verbose_name_plural = '附件库'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['content_type', 'object_id', 'category']),
            models.Index(fields=['content_type', 'object_id', 'group_key']),
            models.Index(fields=['uploader']),
        ]

    def __str__(self):
        return self.display_name or self.filename

    def save(self, *args, **kwargs):
        # 自动填充显示名称
        if not self.display_name and self.file:
            self.display_name = self.file.name.rsplit('/', 1)[-1]
        # 自动记录文件大小
        if self.file and not self.file_size:
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    IMAGE_EXTENSIONS = frozenset({
        'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg',
    })
    CAD_3D_EXTENSIONS = frozenset({'stp', 'step', 'igs', 'iges'})

    @property
    def filename(self):
        """从路径中提取原始文件名"""
        return self.file.name.rsplit('/', 1)[-1] if self.file else ''

    @property
    def extension(self):
        """文件扩展名（小写）"""
        return self.filename.rsplit('.', 1)[-1].lower() if self.filename else ''

    @property
    def is_image(self):
        """是否为常见图片格式"""
        return self.extension in self.IMAGE_EXTENSIONS

    @property
    def preview_kind(self):
        """
        在线预览器类型，供 attachment:viewer 路由分发。

        当前仅 'cad3d'；未来可扩展 'pdf' / 'image' 等，无需改 URL。
        空字符串表示不支持在线预览。
        """
        if self.extension in self.CAD_3D_EXTENSIONS:
            return 'cad3d'
        return ''

    @property
    def can_preview_3d(self):
        return self.preview_kind == 'cad3d'

    @property
    def file_icon_class(self):
        if self.can_preview_3d:
            return 'ti ti-box'
        if self.is_image:
            return 'ti ti-photo'
        return 'ti ti-file'

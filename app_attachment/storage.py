"""
文件存储路径生成器

通过 AttachmentConfig.folder_id_resolver 回调实现通用化，
各业务模块在注册时注入自己的文件夹 ID 计算逻辑。
"""
import os
import re
from django.utils import timezone
from django.core.files.storage import FileSystemStorage


# ==========================================
# Monkey Patch：文件名冲突时使用 (1), (2) 数字后缀
# ==========================================
def custom_get_available_name(self, name, max_length=None):
    dir_name, file_name = os.path.split(name)
    file_root, file_ext = os.path.splitext(file_name)

    counter = 1
    while self.exists(name):
        name = os.path.join(dir_name, f"{file_root}({counter}){file_ext}")
        counter += 1
        if max_length and len(name) > max_length:
            break
    return name


FileSystemStorage.get_available_name = custom_get_available_name


# ==========================================
# 路径生成
# ==========================================
def upload_file_path(instance, filename):
    """
    通用文件路径生成器。

    - Attachment 模型：通过 GFK parent 获取业务对象，
      调用 config.folder_id_resolver 确定目录
    - 其他模型（如 knowledge_base.Document）：使用 pk
    """
    base_name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^\w一-龥\-\(\)\.]', '_', base_name)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    clean_name = clean_name[:60]
    date_path = timezone.now().strftime("%Y-%m-%d")

    if instance._meta.model_name == 'attachment':
        model_name, folder_id = _resolve_attachment_path(instance)
    else:
        model_name = instance._meta.model_name
        folder_id = str(instance.id) if instance.id else 'temp_new'

    return os.path.join('upload_files', model_name, folder_id, date_path, f"{clean_name}{ext}")


def _resolve_attachment_path(instance):
    """通过注册表查找 folder_id_resolver 确定路径"""
    try:
        parent = instance.parent
    except Exception:
        parent = None

    if parent is None:
        obj_id = getattr(instance, 'object_id', None)
        return ('attachment', str(obj_id) if obj_id else 'unlinked')

    model_name = parent._meta.model_name

    # 尝试从注册表获取配置
    try:
        from .registry import get_attachment_config_for_model
        config = get_attachment_config_for_model(type(parent))
        if config and config.folder_id_resolver:
            folder_id = config.folder_id_resolver(parent)
            return (model_name, folder_id)
    except Exception:
        pass

    # 兜底：使用父对象的 pk
    return (model_name, str(parent.pk))

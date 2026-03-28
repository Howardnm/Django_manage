import os
import re
from django.utils import timezone
from django.core.files.storage import FileSystemStorage

# ==========================================
# 核心底层修复：Monkey Patch Django 的存储类
# ==========================================
def custom_get_available_name(self, name, max_length=None):
    """
    重写 Django 底层的文件名冲突处理逻辑
    不再追加 _random_string，而是使用 (1), (2) 格式
    """
    dir_name, file_name = os.path.split(name)
    file_root, file_ext = os.path.splitext(file_name)

    counter = 1
    # 只要文件已存在，就不断递增数字后缀
    while self.exists(name):
        # 生成新路径，例如: path/to/file(1).pdf
        name = os.path.join(dir_name, f"{file_root}({counter}){file_ext}")
        counter += 1
        
        # 长度检查（防止异常情况）
        if max_length and len(name) > max_length:
            break
            
    return name

# 将自定义逻辑注入到 Django 的 FileSystemStorage 类中
# 这样整个项目所有上传文件都会生效，且不需要修改 settings.py
FileSystemStorage.get_available_name = custom_get_available_name


# ==========================================
# 原有的路径生成逻辑
# ==========================================
def upload_file_path(instance, filename):
    """
    文件路径生成器
    现在只需负责生成“理想中”的路径，冲突处理已由上面的补丁接管。
    """
    # 1. 拆分文件名和后缀
    base_name, ext = os.path.splitext(filename)

    # 2. 清洗文件名 (保留中文、括号、点、横杠，不再移除点以便支持 .drawio.png)
    # 将除了字母、数字、汉字、横杠、括号、点以外的字符替换为下划线
    clean_name = re.sub(r'[^\w\u4e00-\u9fa5\-\(\)\.]', '_', base_name)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    clean_name = clean_name[:60]

    # 3. 获取基础路径信息
    date_path = timezone.now().strftime("%Y-%m-%d")
    model_name = instance._meta.model_name
    folder_id = "common"

    # 根据不同模型确定文件夹 ID (原有逻辑)
    if hasattr(instance, 'repository') and instance.repository:
        folder_id = str(instance.repository.project.id)
    elif hasattr(instance, 'project') and instance.project:
        folder_id = str(instance.project.id)
    elif hasattr(instance, 'grade_name'):
        folder_id = str(instance.id) if instance.id else 'temp_new'
    elif hasattr(instance, 'material'):
        folder_id = str(instance.material.id)
    elif hasattr(instance, 'oem'):
        folder_id = str(instance.oem.id)
    elif hasattr(instance, 'formula'):
        folder_id = str(instance.formula.id)
    elif hasattr(instance, 'combination_code'):
        folder_id = str(instance.id) if instance.id else 'temp_new'
    elif hasattr(instance, 'model_name') and hasattr(instance, 'warehouse_code'):
        folder_id = str(instance.id) if instance.id else 'temp_new'
    elif model_name == 'document':
        folder_id = str(instance.id) if instance.id else 'temp_new'

    # 4. 返回初始路径
    # 哪怕这个路径已存在，Django 现在的存储系统也会调用我们上面补丁里的代码来重命名。
    return os.path.join('upload_files', model_name, folder_id, date_path, f"{clean_name}{ext}")

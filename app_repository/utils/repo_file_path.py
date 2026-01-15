import os
import uuid


def repo_file_path(instance, filename):
    """
    动态生成文件路径:
    格式: repository/{模型名}/{年月}/{uuid}.ext
    例如: repository/materiallibrary/202310/a1b2c3d4.pdf
    """
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex[:10]}.{ext}"

    # 获取当前年月日，避免单文件夹文件过多
    from django.utils import timezone
    date_path = timezone.now().strftime("%Y-%m-%d")

    # instance._meta.model_name 会自动获取 model 的类名小写 (e.g., 'materiallibrary')
    return os.path.join('repository', instance._meta.model_name, date_path, filename)
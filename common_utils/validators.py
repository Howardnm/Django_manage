"""
Shim: 重导出到 app_attachment.validators，保持旧 migration 兼容。
新代码请直接使用: from app_attachment.validators import validate_file_size
"""
from app_attachment.validators import validate_file_size  # noqa: F401

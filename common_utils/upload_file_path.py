"""
Shim: 重导出到 app_attachment.storage，保持旧 migration 兼容。
新代码请直接使用: from app_attachment.storage import upload_file_path
"""
from app_attachment.storage import upload_file_path  # noqa: F401

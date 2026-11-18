from django.core.exceptions import ValidationError

# 前端 data-max-bytes 用同一对常量，避免选文件时的上限和服务端不一致。
MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def validate_file_size(value):
    """限制文件大小。默认 50MB。"""
    if value.size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"文件大小不能超过 {MAX_UPLOAD_MB}MB。当前文件大小: {value.size / 1024 / 1024:.2f}MB"
        )

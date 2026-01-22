from django.core.exceptions import ValidationError

def validate_file_size(value):
    """
    限制文件大小的验证器
    默认限制: 50MB
    """
    limit_mb = 50
    limit = limit_mb * 1024 * 1024
    
    if value.size > limit:
        raise ValidationError(f"文件大小不能超过 {limit_mb}MB。当前文件大小: {value.size / 1024 / 1024:.2f}MB")

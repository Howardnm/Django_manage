import mimetypes

from django.apps import AppConfig


class AppAttachmentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_attachment'
    verbose_name = '附件管理'

    def ready(self):
        # Windows / 部分系统未注册 .wasm MIME，OCCT Worker 会加载失败
        mimetypes.add_type('application/wasm', '.wasm')
        # 导入信号，使父对象删除时自动级联清理附件生效
        import app_attachment.signals  # noqa: F401

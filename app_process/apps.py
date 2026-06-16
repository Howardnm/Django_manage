from django.apps import AppConfig

class AppProcessConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_process'
    verbose_name = '工艺库'

    def ready(self):
        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_process.models import ScrewCombination, ProcessProfile
        from app_process.mixins import ProcessAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=ScrewCombination,
            access_mixin=ProcessAccessMixin,
            view_permission='app_process.view_screwcombination',
            add_permission='app_process.add_screwcombination',
            delete_permission='app_process.change_screwcombination',
            categories=[
                ('DRAWING', '螺杆图纸'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda s: str(s.pk),
        ))

        register_attachment(AttachmentConfig(
            parent_model=ProcessProfile,
            access_mixin=ProcessAccessMixin,
            view_permission='app_process.view_processprofile',
            add_permission='app_process.add_processprofile',
            delete_permission='app_process.change_processprofile',
            categories=[
                ('REPORT', '工艺报告'),
                ('DATA', '工艺数据'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda p: str(p.pk),
        ))

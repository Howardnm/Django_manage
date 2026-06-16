from django.apps import AppConfig

class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material'
    verbose_name = '材料库'

    def ready(self):
        # 信号监听逻辑已经迁移到 app_material_api 模块
        # app_material 现在只保留模型定义和基础业务逻辑

        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_material.models.material import MaterialLibrary
        from app_material.mixins import MaterialAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=MaterialLibrary,
            access_mixin=MaterialAccessMixin,
            view_permission='app_material.view_materiallibrary',
            add_permission='app_material.add_materiallibrary',
            delete_permission='app_material.change_materiallibrary',
            categories=[
                ('TDS', 'TDS 技术数据表'),
                ('MSDS', 'MSDS 安全数据表'),
                ('RoHS', 'RoHS 环保报告'),
                ('UL', 'UL 认证'),
                ('REACH', 'REACH 报告'),
                ('COC', 'COC 符合证明'),
                ('SPEC', '产品规格书'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda m: str(m.pk),
        ))

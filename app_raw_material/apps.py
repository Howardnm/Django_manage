from django.apps import AppConfig

class AppRawMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_raw_material'
    verbose_name = '原材料库'

    def ready(self):
        import app_raw_material.signals

        # 注册自动补全
        from common_utils.autocomplete_registry import register_autocomplete
        from app_raw_material.models import RawMaterial
        from django.db.models import Q

        register_autocomplete('raw_material',
            lambda q: RawMaterial.objects.filter(
                Q(name__icontains=q) | Q(model_name__icontains=q)),
            lambda r: {'value': r.pk, 'text': f'{r.name} {r.model_name or ""} ({r.category.name})'},
            'raw_material_detail')

        # 注册附件配置
        from app_attachment.registry import register_attachment
        from app_attachment.configs import AttachmentConfig
        from app_raw_material.models import RawMaterial
        from app_raw_material.mixins import RawMaterialAccessMixin

        register_attachment(AttachmentConfig(
            parent_model=RawMaterial,
            access_mixin=RawMaterialAccessMixin,
            view_permission='app_raw_material.view_rawmaterial',
            add_permission='app_raw_material.add_rawmaterial',
            delete_permission='app_raw_material.change_rawmaterial',
            categories=[
                ('TDS', 'TDS 技术数据表'),
                ('MSDS', 'MSDS 安全数据表'),
                ('RoHS', 'RoHS 环保报告'),
                ('OTHER', '其他文件'),
            ],
            folder_id_resolver=lambda m: str(m.pk),
        ))

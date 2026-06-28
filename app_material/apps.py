from django.apps import AppConfig

class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material'
    verbose_name = '材料库'

    def ready(self):
        # 注册自动补全（供 common_utils MaterialAutocompleteView 使用）
        from common_utils.autocomplete_registry import register_autocomplete, make_autocomplete_access_filter
        from app_material.mixins import MaterialAccessMixin
        from app_material.models.material import MaterialLibrary, ApplicationScenario, TestConfig, MaterialCharacteristic
        from django.db.models import Q

        register_autocomplete('material',
            lambda q: MaterialLibrary.objects.only('pk', 'grade_name', 'manufacturer').filter(
                Q(grade_name__icontains=q) | Q(manufacturer__icontains=q)),
            lambda m: {'value': m.pk, 'text': f'{m.grade_name} ({m.manufacturer})'},
            'material_detail',
            access_filter=make_autocomplete_access_filter(MaterialAccessMixin),
        )

        register_autocomplete('scenario',
            lambda q: ApplicationScenario.objects.only('pk', 'name').filter(name__icontains=q),
            lambda s: {'value': s.pk, 'text': s.name})

        register_autocomplete('test_config',
            lambda q: TestConfig.objects.select_related('category').only(
                'pk', 'name', 'standard', 'condition', 'category__name'
            ).filter(Q(name__icontains=q) | Q(standard__icontains=q)),
            lambda t: {'value': t.pk,
                'text': f'[{t.category.name}] {t.name} - {t.standard}{f" ({t.condition})" if t.condition else ""}'})

        register_autocomplete('characteristic',
            lambda q: MaterialCharacteristic.objects.only('pk', 'name').filter(name__icontains=q),
            lambda c: {'value': c.pk, 'text': c.name})

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

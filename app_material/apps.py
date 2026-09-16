from django.apps import AppConfig

class AppMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_material'
    verbose_name = '材料库'

    def ready(self):
        # 挂载材料库缓存失效信号
        import app_material.signals  # noqa: F401

        # 注册自动补全（供 common_utils MaterialAutocompleteView 使用）
        from common_utils.autocomplete_registry import register_autocomplete, make_autocomplete_access_filter
        from app_material.mixins import MaterialAccessMixin
        from app_material.models.material import (MaterialLibrary, ApplicationScenario, TestConfig,
                                                  MaterialCharacteristic, MaterialType)
        from django.db.models import Q

        register_autocomplete('material',
            lambda q: MaterialLibrary.objects.only('pk', 'grade_name', 'manufacturer').filter(
                Q(grade_name__icontains=q) | Q(manufacturer__icontains=q)),
            lambda m: {'value': m.pk, 'text': f'{m.grade_name} ({m.manufacturer})'},
            'material_detail',
            access_filter=make_autocomplete_access_filter(MaterialAccessMixin),
        )

        def _filter_material_import(qs, params):
            """material_import 选择器的具名筛选字段（多字段搜索模式）。

            前端只发送非空字段，因此缺省即不过滤（等价于浏览全部）。
            """
            grade_name = params.get('grade_name', '').strip()
            if grade_name:
                qs = qs.filter(grade_name__icontains=grade_name)
            manufacturer = params.get('manufacturer', '').strip()
            if manufacturer:
                qs = qs.filter(manufacturer__icontains=manufacturer)
            category_id = params.get('category_id', '').strip()
            if category_id.isdigit():
                qs = qs.filter(category_id=category_id)
            return qs

        # 搜索选择器表格里 M2M 列表列的展示长度上限（超出截断加省略号）
        M2M_LIST_CAP = 20

        def _join_names(manager, cap=M2M_LIST_CAP):
            """把 M2M 名称拼成表格单元格文本，超长截断。

            表格带 text-nowrap，多值全量展开会把表格撑得很宽，故限制展示长度。
            """
            names = [obj.name for obj in manager.all()]
            text = '、'.join(names)
            if len(text) > cap:
                text = text[:cap] + '…'
            return text

        # 导入数据选择器专用：与 'material' 同源查询，但额外吐出表格列所需字段。
        # 单独注册一个 key，避免改动 'material' 的契约（app_project/forms.py 的远程搜索在用它）。
        register_autocomplete('material_import',
            lambda q: MaterialLibrary.objects.only(
                'pk', 'grade_name', 'manufacturer',
                'sap_material_code', 'material_color_name',
            ).prefetch_related('characteristics', 'scenarios').filter(
                Q(grade_name__icontains=q) | Q(manufacturer__icontains=q)),
            lambda m: {
                'value': m.pk,
                'text': m.grade_name,
                'grade_name': m.grade_name,
                'manufacturer': m.manufacturer,
                'sap_material_code': m.sap_material_code,
                'material_color_name': m.material_color_name,
                'characteristics': _join_names(m.characteristics),
                'scenarios': _join_names(m.scenarios),
            },
            'material_detail',
            access_filter=make_autocomplete_access_filter(MaterialAccessMixin),
            filter_fn=_filter_material_import,
        )

        # 材料类型：供搜索选择器的 remote-select 筛选字段使用
        register_autocomplete('material_type',
            lambda q: MaterialType.objects.only('pk', 'name').filter(name__icontains=q),
            lambda t: {'value': t.pk, 'text': t.name})

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

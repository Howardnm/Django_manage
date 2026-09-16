from django.apps import AppConfig

class AppRawMaterialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_raw_material'
    verbose_name = '原材料库'

    def ready(self):
        # 注册自动补全
        from common_utils.autocomplete_registry import register_autocomplete, make_autocomplete_access_filter
        from app_raw_material.mixins import RawMaterialAccessMixin, RawMaterialPickerAccessMixin
        from app_raw_material.models import RawMaterial
        from app_raw_material.services import RawMaterialPriceService
        from django.db.models import Q

        def _build_raw_material_qs(query):
            """按 名称 / 型号 / 内部物料编码 模糊匹配。

            warehouse_code 已经在候选项文案里展示，必须一并参与匹配 ——
            原先只搜 name 与 model_name，导致「输编码搜不到」。
            """
            return RawMaterial.objects.select_related('category').only(
                'pk', 'name', 'model_name', 'category__name', 'warehouse_code'
            ).filter(
                Q(name__icontains=query)
                | Q(model_name__icontains=query)
                | Q(warehouse_code__icontains=query)
            )

        def _format_raw_materials(materials):
            """批量格式化候选项 —— 价格一次装载，逐条查价会变成 N+1。

            自动补全每敲一次键都会打这个接口；价格不落库（RawMaterial 上已删掉
            反规范化缓存列），只能实时算，所以必须走 RawMaterialPriceLookup 批量路径。
            """
            materials = list(materials)
            prices = RawMaterialPriceService.for_ids([m.pk for m in materials])

            results = []
            for m in materials:
                text = ' '.join(part for part in (m.name, m.model_name) if part)
                text += f' ({m.category.name})'
                if m.warehouse_code:
                    text += f' ({m.warehouse_code})'
                price = prices.latest(m)
                # latest() 的契约：None = 无报价，Decimal('0.00') 是有效价格
                if price is not None:
                    text += f' (¥{price:.2f})'
                results.append({
                    'value': m.pk,
                    'text': text,
                    'category_name': m.category.name,
                })
            return results

        register_autocomplete('raw_material',
            _build_raw_material_qs,
            lambda r: _format_raw_materials([r])[0],
            'raw_material_detail',
            access_filter=make_autocomplete_access_filter(RawMaterialPickerAccessMixin),
            bulk_formatter_fn=_format_raw_materials,
        )

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

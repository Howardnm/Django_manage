import re
from decimal import Decimal, ROUND_HALF_UP

from django.apps import AppConfig
from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce, Concat


def _wildcard_raw_materials(query):
    """通配符同时落在「名称 型号 内部编码 工厂代码」上。

    工厂是多对多，先按每个工厂拼一行再收成不重复的物料，
    避免一个物料因为挂了两个工厂在下拉里出现两次。
    没挂工厂的物料补一条空工厂代码，否则纯名称型号的通配会把它漏掉。
    """
    from app_raw_material.models import RawMaterial

    pattern = re.escape(re.sub(r'\*+', '*', query)).replace(r'\*', '.*').replace(r'\?', '.')
    parts = [
        Coalesce('name', Value('')), Value(' '),
        Coalesce('model_name', Value('')), Value(' '),
        Coalesce('warehouse_code', Value('')), Value(' '),
        Coalesce('plants__code', Value('')),
    ]
    per_plant = RawMaterial.objects.annotate(
        _text_search=Concat(*parts, output_field=CharField())
    ).filter(_text_search__iregex=pattern)
    no_plant = RawMaterial.objects.filter(plants__isnull=True).annotate(
        _text_search=Concat(
            Coalesce('name', Value('')), Value(' '),
            Coalesce('model_name', Value('')), Value(' '),
            Coalesce('warehouse_code', Value('')), Value(' '),
            Value(''),
            output_field=CharField(),
        )
    ).filter(_text_search__iregex=pattern)
    return RawMaterial.objects.filter(
        Q(pk__in=per_plant.values('pk')) | Q(pk__in=no_plant.values('pk'))
    )


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
        from common_utils.text_search import text_q

        def _build_raw_material_qs(query):
            """按 名称 / 型号 / 内部物料编码 模糊匹配。

            warehouse_code 已经在候选项文案里展示，必须一并参与匹配 ——
            原先只搜 name 与 model_name，导致「输编码搜不到」。
            有 ``*`` / ``?`` 时再把工厂代码拼进同一段，见 ``_wildcard_raw_materials``。
            """
            base = RawMaterial.objects.select_related('category').prefetch_related(
                'plants'
            ).only(
                'pk', 'name', 'model_name', 'category__name', 'warehouse_code'
            )
            if '*' in query or '?' in query:
                return base.filter(pk__in=_wildcard_raw_materials(query).values('pk'))
            return text_q(base, query, 'name', 'model_name', 'warehouse_code')

        def _format_raw_materials(materials):
            """批量格式化候选项 —— 价格一次装载，逐条查价会变成 N+1。

            自动补全每敲一次键都会打这个接口；价格不落库（RawMaterial 上已删掉
            反规范化缓存列），只能实时算，所以必须走 RawMaterialPriceLookup 批量路径。
            """
            materials = list(materials)
            prices = RawMaterialPriceService.for_ids([m.pk for m in materials])
            stock_totals = RawMaterial.unrestricted_stock_totals(m.pk for m in materials)

            results = []
            for m in materials:
                text = ' '.join(part for part in (m.name, m.model_name) if part)
                text += f' ({m.category.name})'
                if m.warehouse_code:
                    text += f' ({m.warehouse_code})'
                # 只展示工厂代码。多个工厂合成一对括号，按代码排序、顿号分隔；
                # 未挂工厂则不加空括号。价格仍是跨工厂均价，不按工厂拆开。
                plant_codes = sorted(p.code for p in m.plants.all() if p.code)
                if plant_codes:
                    text += f' ({"、".join(plant_codes)})'
                price = prices.latest(m)
                # latest() 的契约：None = 无报价，Decimal('0.00') 是有效价格
                if price is not None:
                    text += f' (¥{price:.2f})'
                total = stock_totals.get(m.pk)
                results.append({
                    'value': m.pk,
                    'text': text,
                    'category_name': m.category.name,
                    # 没有快照是 null，不能收成 0；有快照则四舍五入到整数。
                    'stock_qty': (
                        None if m.pk not in stock_totals
                        else int(Decimal(total).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    ),
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

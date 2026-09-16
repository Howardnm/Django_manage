from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect
from django.db.models import Q, Subquery, OuterRef, DecimalField

from app_raw_material.models import PriceAvgConfig, RawMaterial, RawMaterialPriceRecord, RawMaterialProperty, Supplier
from app_raw_material.forms import RawMaterialForm, RawMaterialPropertyFormSet
from app_raw_material.utils.filters import RawMaterialFilter
from app_raw_material.mixins import RawMaterialAccessMixin
from common_utils.constants import STD_TABS

class RawMaterialListView(RawMaterialAccessMixin, ListView):
    """原材料列表：仅限定的研发中心角色组可见，L4/L5 关闭"""
    permission_required = 'app_raw_material.view_rawmaterial'
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/list.html'
    context_object_name = 'materials'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 基础查询 (enforce_dept_isolation=False 已在 Mixin 定义)
        # price_records 必须 prefetch：模板逐个读 material.latest_price / avg_price，
        # 而价格是实时算的 —— 不预取的话每个原材料各打一次查询（N+1）
        qs = super().get_queryset().select_related('category', 'supplier').prefetch_related(
            'suitable_materials', 'properties__test_config', 'price_records'
        ).order_by('-created_at')
        
        # 2. 动态性能排序逻辑 (保持)
        sort_param = self.request.GET.get('sort', '')
        metric_map = {
            'density': ('密度', 'val_density'),
            'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融指数', 'val_melt'),
            'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'),
            'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'),
            'hdt': ('变形温度', 'val_hdt'),
        }

        if sort_param:
            clean_sort = sort_param.lstrip('-')
            if clean_sort in metric_map:
                keyword, field_name = metric_map[clean_sort]
                current_std = self.request.GET.get('std', 'ISO')
                std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
                std_query = Q()
                for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)
                
                qs = qs.annotate(**{
                    field_name: Subquery(
                        RawMaterialProperty.objects.filter(
                            std_query, raw_material=OuterRef('pk'),
                            test_config__name__icontains=keyword
                        ).order_by('-id').values('value')[:1],
                        output_field=DecimalField()
                    )
                })

        # 3. 按成本排序：分页列表无法在 Python 侧排序，需要 SQL 表达式
        if sort_param.lstrip('-') == 'latest_price':
            qs = RawMaterial.annotate_latest_price(qs)

        self.filterset = RawMaterialFilter(self.request.GET, queryset=qs, request=self.request)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

        for mat in context['materials']:
            props = mat.properties.all()
            def find_val_in_memory(keyword):
                for p in props:
                    if keyword in p.test_config.name:
                        if any(k in p.test_config.standard for k in std_keywords):
                            return p.value
                return None

            if not hasattr(mat, 'val_density'): mat.val_density = find_val_in_memory("密度")
            if not hasattr(mat, 'val_ash'): mat.val_ash = find_val_in_memory("灰分")
            if not hasattr(mat, 'val_melt'): mat.val_melt = find_val_in_memory("熔融指数")
            if not hasattr(mat, 'val_tensile'): mat.val_tensile = find_val_in_memory("拉伸强度")
            if not hasattr(mat, 'val_flex_strength'): mat.val_flex_strength = find_val_in_memory("弯曲强度")
            if not hasattr(mat, 'val_flex_modulus'): mat.val_flex_modulus = find_val_in_memory("弯曲模量")
            if not hasattr(mat, 'val_impact'): mat.val_impact = find_val_in_memory("冲击")
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("热变形")

        context.update({
            'cart_raw_material_ids': self.request.session.get('cart_raw_materials_v2', []),
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'current_std': current_std,
            'std_tabs': STD_TABS,
        })
        return context

class RawMaterialDetailView(RawMaterialAccessMixin, DetailView):
    """详情：仅限定的研发中心角色组可见"""
    permission_required = 'app_raw_material.view_rawmaterial'
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/detail.html'
    context_object_name = 'material'

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'supplier').prefetch_related(
            'properties__test_config', 'price_records__plant', 'stock_snapshots__plant'
        )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        import calendar
        import json
        from collections import defaultdict
        from decimal import Decimal

        context = super().get_context_data(**kwargs)
        material = self.object

        # 日聚合与单条价格统一走价格服务（唯一实现），并复用 get_queryset 的
        # price_records prefetch —— 0 条新查询
        from app_raw_material.services import RawMaterialPriceService
        prices = RawMaterialPriceService.for_material(material)

        # 只用 .all() 拿 prefetch 缓存；filter/order_by 会绕过它重建查询
        all_records = list(material.price_records.all())
        ascending = sorted(all_records, key=lambda r: r.date)
        context['price_records'] = ascending
        context['recent_records'] = sorted(all_records, key=lambda r: r.date, reverse=True)[:5]
        context['avg_months'] = PriceAvgConfig.get().months

        # 全局走势线：按日期取各工厂均值（口径同「最新单价」的日聚合）
        global_trend = [
            {
                'x': calendar.timegm(day.timetuple()) * 1000,
                'y': float(day_avg.quantize(Decimal('0.01'))),
                'source': '',
            }
            for day, day_avg in prices.series().get(material.pk, [])
        ]

        # 按工厂分组构建多 series 图表数据（数组保证顺序，避免 JS for-in 数字key排序问题）
        plant_series = defaultdict(list)
        for record in ascending:
            plant_name = str(record.plant) if record.plant else '未指定工厂'
            plant_series[plant_name].append({
                'x': calendar.timegm(record.date.timetuple()) * 1000,
                'y': float(record.price),
                'source': record.source or '',
            })
        series_list = []
        if len(global_trend) >= 2:
            series_list.append({'name': '全局均值', 'data': global_trend})
        for plant_name in plant_series:
            series_list.append({'name': plant_name, 'data': plant_series[plant_name]})
        context['price_series_json'] = json.dumps(series_list)

        # 价格概览：各工厂最新价 / 均价 —— 复用同一个 prices 实例，
        # 避免逐工厂重建查表（原路径每个工厂各打一次聚合）
        plant_prices = [
            {
                'plant': plant,
                'latest': prices.latest(material, plant),
                'avg': prices.avg(material, plant),
            }
            for plant in material.plants_with_prices
        ]
        context['plant_prices'] = plant_prices

        # ── 库存概览 ──
        stock_plants = material.plants_with_stock
        plant_stocks = []
        latest_synced_at = None
        for plant in stock_plants:
            snapshots = material.stock_for_plant(plant).order_by(
                'storage_location', 'batch'
            )
            clabs_total = material.stock_total_for_plant(plant)
            eisbe_total = material.stock_safety_for_plant(plant)
            available = material.stock_available_above_safety(plant)

            # 记录最新同步时间
            first = snapshots.first()
            if first and (latest_synced_at is None or first.synced_at > latest_synced_at):
                latest_synced_at = first.synced_at

            plant_stocks.append({
                'plant': plant,
                'snapshots': snapshots,
                'clabs_total': clabs_total,
                'eisbe_total': eisbe_total,
                'available': available,
                'is_below_safety': available < 0,
            })
        context['plant_stocks'] = plant_stocks
        context['latest_stock_synced_at'] = latest_synced_at

        return context

class RawMaterialCreateView(RawMaterialAccessMixin, CreateView):
    """创建：需 add_rawmaterial 权限，主要供采购/技术经理使用"""
    permission_required = 'app_raw_material.add_rawmaterial'
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST)
        else:
            # 【修改】预留 4 行空表单。
            # 改实例属性 —— 改类属性会跨请求泄漏到同一 worker 的其他请求。
            formset = RawMaterialPropertyFormSet(queryset=RawMaterialProperty.objects.none())
            formset.extra = 4
            context['property_formset'] = formset
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        property_formset = context['property_formset']
        with transaction.atomic():
            self.object = form.save()
            if property_formset.is_valid():
                property_formset.instance = self.object
                property_formset.save()
            else:
                # 事务块内返回必须显式回滚，否则主表会被提交，
                # 留下一条没有物性数据的半成品原材料
                transaction.set_rollback(True)
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "原材料已添加")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})

class RawMaterialDuplicateView(RawMaterialAccessMixin, UpdateView):
    """复制：需增加权限"""
    permission_required = 'app_raw_material.add_rawmaterial'
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    @property
    def original_material(self):
        """鉴权后懒加载原材料对象"""
        if not hasattr(self, '_original_material'):
            self._original_material = self.get_object()
        return self._original_material

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制原材料'

        # 如果是 GET 请求，预填充 FormSet 数据
        if not self.request.POST:
            prop_initial = [{
                'test_config': p.test_config, 'value': p.value, 'value_text': p.value_text,
                'min_value': p.min_value, 'max_value': p.max_value,
                'min_value_text': p.min_value_text, 'max_value_text': p.max_value_text,
                'test_date': p.test_date, 'remark': p.remark,
            } for p in self.original_material.properties.all()]
            context['property_formset'] = RawMaterialPropertyFormSet(initial=prop_initial)
            context['property_formset'].extra = len(prop_initial)
        else:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST)
        return context

    def get_initial(self):
        initial = super().get_initial()
        initial.update({
            'name': f"{self.original_material.name} (副本)",
            'model_name': self.original_material.model_name,
            'warehouse_code': None,
            'category': self.original_material.category,
            'supplier': self.original_material.supplier,
            'usage_method': self.original_material.usage_method,
            'latest_price': self.original_material.latest_price,
            'purchase_date': self.original_material.purchase_date,
            'suitable_materials': self.original_material.suitable_materials.all(),
        })
        return initial

    def form_valid(self, form):
        context = self.get_context_data()
        property_formset = context['property_formset']
        with transaction.atomic():
            form.instance.pk = None
            self.object = form.save()
            if property_formset.is_valid():
                property_formset.instance = self.object
                property_formset.save()
            else:
                # 同新增：不回滚会留下副本半成品
                transaction.set_rollback(True)
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "原材料已复制并创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})

class RawMaterialUpdateView(RawMaterialAccessMixin, UpdateView):
    """编辑：需 change_rawmaterial 权限"""
    permission_required = 'app_raw_material.change_rawmaterial'
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST, instance=self.object)
        else:
            # 【修改】编辑时额外留 1 行空表单方便添加。
            # 实例属性，勿改类属性（会跨请求泄漏）
            formset = RawMaterialPropertyFormSet(instance=self.object)
            formset.extra = 1
            context['property_formset'] = formset
        return context

    def form_valid(self, form):
        self.check_edit_permission(self.object)
        context = self.get_context_data()
        property_formset = context['property_formset']
        with transaction.atomic():
            self.object = form.save()
            if property_formset.is_valid():
                property_formset.save()
            else:
                # 同新增：不回滚会把主表改动提交、物性改动丢弃
                transaction.set_rollback(True)
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "原材料已更新")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})


class RawMaterialAutocompleteView(RawMaterialAccessMixin, View):
    """Tom Select 远程搜索接口：供应商名称"""
    permission_required = 'app_raw_material.view_rawmaterial'

    def get(self, request):
        model_name = request.GET.get('model')
        query = request.GET.get('q', '')
        results = []
        if model_name == 'supplier':
            queryset = Supplier.objects.filter(
                Q(name__icontains=query)
            ).order_by('name')[:20]
            for item in queryset:
                results.append({'value': item.pk, 'text': str(item)})
        return JsonResponse(results, safe=False)

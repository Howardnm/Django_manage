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

class RawMaterialListView(RawMaterialAccessMixin, ListView):
    """原材料列表：仅限定的研发中心角色组可见，L4/L5 关闭"""
    permission_required = 'app_raw_material.view_rawmaterial'
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/list.html'
    context_object_name = 'materials'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 基础查询 (enforce_dept_isolation=False 已在 Mixin 定义)
        qs = super().get_queryset().select_related('category', 'supplier').prefetch_related(
            'suitable_materials', 'properties__test_config'
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
            'current_std': current_std
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
            'properties__test_config', 'price_records', 'stock_snapshots__plant'
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

        price_records = material.price_records.order_by('date')
        context['price_records'] = price_records
        context['recent_records'] = material.price_records.select_related('plant').order_by('-date')[:5]
        context['avg_months'] = PriceAvgConfig.get().months

        # 全局走势线：按日期取各工厂均值
        from collections import defaultdict as dd
        date_prices = dd(list)
        for record in price_records:
            date_prices[record.date].append(record.price)
        global_trend = []
        for d in sorted(date_prices.keys()):
            avg_price = sum(date_prices[d], Decimal('0')) / len(date_prices[d])
            global_trend.append({
                'x': calendar.timegm(d.timetuple()) * 1000,
                'y': float(avg_price.quantize(Decimal('0.01'))),
                'source': '',
            })

        # 按工厂分组构建多 series 图表数据（数组保证顺序，避免 JS for-in 数字key排序问题）
        plant_series = defaultdict(list)
        for record in price_records.select_related('plant'):
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

        # 价格概览：各工厂最新价 / 均价
        plants = material.plants_with_prices
        plant_prices = []
        for plant in plants:
            plant_prices.append({
                'plant': plant,
                'latest': material.latest_price_for_plant(plant),
                'avg': material.avg_price_for_plant(plant),
            })
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
            # 【修改】预留 4 行空表单
            RawMaterialPropertyFormSet.extra = 4
            context['property_formset'] = RawMaterialPropertyFormSet(queryset=RawMaterialProperty.objects.none())
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
            # 【修改】编辑时，如果已有数据少于4行，补足到4行 (这里简单设为1，方便添加)
            RawMaterialPropertyFormSet.extra = 1
            context['property_formset'] = RawMaterialPropertyFormSet(instance=self.object)
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

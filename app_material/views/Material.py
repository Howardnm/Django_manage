from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, DecimalField
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.http import JsonResponse
import json

from app_material.forms import MaterialForm, MaterialDataFormSet, MaterialProcessingConditionForm
from app_material.models.material import MaterialLibrary, MaterialDataPoint
from app_material.utils.filters import MaterialFilter
from app_material.utils.search_picker_config import for_material_import
from app_formula.models import FormulaTestResult, LabFormula
from app_material.mixins import MaterialAccessMixin, MaterialFormErrorMixin
from app_material.services.material_cache import MaterialCache
from common_utils.constants import STD_TABS


# 「导入数据」暂存来源牌号 id 的 session key（仅新增页使用，GET 消费后即清除）
SESSION_IMPORT_KEY = 'material_import'

# 导入时从来源牌号带过来的标量字段。
# 刻意不含 grade_name / manufacturer / sap_material_code —— 它们是当前材料的身份信息；
# 也不含 scenarios / characteristics / 加工条件，见计划文档的决策表。
IMPORT_SCALAR_FIELDS = [
    'category', 'flammability',
    'material_color_name', 'pantone_code', 'rgb_value',
    'description',
]


def _material_data_point_rows(source):
    """把来源牌号的物性数据转成 MaterialDataFormSet 的 initial 列表。

    键名与表单字段名一致（含 'test_config'），直接可作 formset initial。
    落库时须先经 _as_model_kwargs() 转换。
    """
    return [
        {
            'test_config': p.test_config_id,
            'value': p.value,
            'value_text': p.value_text,
            'min_value': p.min_value,
            'max_value': p.max_value,
            'min_value_text': p.min_value_text,
            'max_value_text': p.max_value_text,
            'remark': p.remark,
        }
        for p in source.properties.all()
    ]


def _as_model_kwargs(row):
    """把 formset 形状的行转成 MaterialDataPoint 的建参。

    外键必须按 test_config_id 传：按字段名传裸主键会触发
    ForwardManyToOneDescriptor 的 ValueError（"must be a TestConfig instance"）。
    """
    kwargs = dict(row)
    kwargs['test_config_id'] = kwargs.pop('test_config')
    return kwargs


class MaterialListView(MaterialAccessMixin, ListView):
    """材料列表：全员内部可见，不设部门隔离。"""
    permission_required = 'app_material.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10

    def get_queryset(self):
        # 基类 super().get_queryset() 已处理 identity_required 和 enforce_dept_isolation=False
        qs = super().get_queryset().select_related('category').prefetch_related(
            'scenarios', 'properties', 'properties__test_config'
        )

        sort_param = self.request.GET.get('sort', '')
        metric_map = {
            'density': ('密度', 'val_density'), 'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融指数', 'val_melt'), 'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'), 'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'), 'hdt': ('变形温度', 'val_hdt'),
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
                        MaterialDataPoint.objects.filter(
                            std_query, material=OuterRef('pk'),
                            test_config__name__icontains=keyword
                        ).order_by('-id').values('value')[:1],
                        output_field=DecimalField()
                    )
                })

        self.filterset = MaterialFilter(self.request.GET, queryset=qs, request=self.request)
        return self.filterset.qs.order_by('-created_at') if not sort_param else self.filterset.qs

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
            'cart_material_ids': self.request.session.get('cart_materials_v2', []),
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'current_std': current_std,
            'std_tabs': STD_TABS,
        })
        return context


class MaterialCreateView(MaterialFormErrorMixin, MaterialAccessMixin, CreateView):
    """录入材料：需具备 add_materiallibrary 权限。"""
    permission_required = 'app_material.add_materiallibrary'
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_material/material/material_form.html'

    def _import_source(self):
        """解析 session 中的导入来源牌号；无来源 / 已失效 / 无权访问时返回 None。

        结果缓存在视图实例上，供 get_initial() 与 get_context_data() 共用一次查询。
        """
        if not hasattr(self, '_import_source_cache'):
            source = None
            source_id = self.request.session.get(SESSION_IMPORT_KEY, {}).get('source_id')
            if source_id:
                try:
                    candidate = self.get_queryset().get(pk=source_id)
                    self.check_object_permission(candidate)
                    source = candidate
                except (MaterialLibrary.DoesNotExist, PermissionDenied):
                    # 过期的 session 来源：静默放弃预填，不要因此把录入页打成 403
                    source = None
            self._import_source_cache = source
        return self._import_source_cache

    def get_initial(self):
        initial = super().get_initial()
        source = self._import_source()
        if source:
            initial['category'] = source.category_id
            for field in IMPORT_SCALAR_FIELDS:
                if field != 'category':
                    initial[field] = getattr(source, field)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST)
            context['processing_form'] = MaterialProcessingConditionForm(self.request.POST)
        else:
            source = self._import_source()
            rows = _material_data_point_rows(source) if source else []
            formset = MaterialDataFormSet(
                queryset=MaterialDataPoint.objects.none(), initial=rows)
            # initial 在 ModelFormSet 上只填充 extra 槽位（未绑定时 initial_form_count()
            # 返回 len(queryset)，此处为 0），行数必须显式抬高，否则超出 extra 的行会被
            # 静默丢弃。改实例属性 —— 改类属性会跨请求泄漏到同一 worker 的其他请求。
            formset.extra = max(len(rows), 6)
            context['data_formset'] = formset
            context['processing_form'] = MaterialProcessingConditionForm()
        context.update({
            'page_title': '录入新材料',
            'is_edit': False,
            # 无条件设置：POST 校验失败重渲染时按钮与模态框也必须还在
            'show_import_button': True,
            'search_picker': for_material_import(),
        })
        # 预填只在 GET 消费一次。必须放在最后 —— super() 内的 get_initial() 刚读完 session。
        if not self.request.POST:
            self.request.session.pop(SESSION_IMPORT_KEY, None)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        data_formset = context['data_formset']
        processing_form = context['processing_form']
        with transaction.atomic():
            form.instance.creator = self.request.user  # 记录创建人
            self.object = form.save()
            if data_formset.is_valid():
                data_formset.instance = self.object
                data_formset.save()
            else:
                # 事务块内返回必须显式回滚，否则主表会被提交，留下没有物性数据的半成品材料
                transaction.set_rollback(True)
                messages.error(self.request, self._build_error_message(form, data_formset))
                return self.render_to_response(self.get_context_data(form=form))
            if processing_form.is_valid():
                processing_form.instance.material = self.object
                processing_form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('material_detail', kwargs={'pk': self.object.pk})


class MaterialUpdateView(MaterialFormErrorMixin, MaterialAccessMixin, UpdateView):
    """编辑材料：需具备 change_materiallibrary 权限。"""
    permission_required = 'app_material.change_materiallibrary'
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_material/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        processing_instance = getattr(self.object, 'processing_condition', None)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST, instance=self.object)
            context['processing_form'] = MaterialProcessingConditionForm(self.request.POST, instance=processing_instance)
        else:
            formset = MaterialDataFormSet(instance=self.object)
            formset.extra = 1  # 实例属性，勿改类属性（会跨请求泄漏）
            context['data_formset'] = formset
            context['processing_form'] = MaterialProcessingConditionForm(instance=processing_instance)
        context.update({
            'page_title': f'编辑: {self.object.grade_name}',
            'is_edit': True,
            # 无条件设置：POST 校验失败重渲染时按钮与模态框也必须还在
            'show_import_button': True,
            'search_picker': for_material_import(),
        })
        return context

    def form_valid(self, form):
        self.check_edit_permission(self.object)  # 仅创建人或超管可编辑
        context = self.get_context_data()
        data_formset = context['data_formset']
        processing_form = context['processing_form']
        with transaction.atomic():
            self.object = form.save()
            if data_formset.is_valid():
                data_formset.save()
            else:
                # 事务块内返回必须显式回滚，否则主表改动会被提交
                transaction.set_rollback(True)
                messages.error(self.request, self._build_error_message(form, data_formset))
                return self.render_to_response(self.get_context_data(form=form))
            if processing_form.is_valid():
                processing_form.instance.material = self.object
                processing_form.save()
        messages.success(self.request, f'材料 "{self.object.grade_name}" 保存成功。')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('material_detail', kwargs={'pk': self.object.pk})


class MaterialImportPrepareView(MaterialAccessMixin, View):
    """新增页「导入数据」：校验来源牌号后写入 session，重定向回录入页预填。

    不写库 —— 数据在 MaterialCreateView 的 GET 上被消费成表单 initial，
    用户仍需点「保存数据」才落库。对标 app_formula 的 FormulaImportPrepareView。
    """
    permission_required = 'app_material.add_materiallibrary'
    model = MaterialLibrary

    def post(self, request):
        source_id = request.POST.get('source_material_id')
        if not source_id:
            messages.error(request, '请选择要导入的参考牌号')
            return redirect(reverse('material_add'))
        try:
            source = self.get_queryset().get(pk=source_id)
        except (MaterialLibrary.DoesNotExist, ValueError):
            messages.error(request, '所选参考牌号不存在')
            return redirect(reverse('material_add'))
        self.check_object_permission(source)

        request.session[SESSION_IMPORT_KEY] = {'source_id': source.pk}
        messages.success(request, f'已从牌号「{source.grade_name}」载入数据，请确认后保存。')
        return redirect(reverse('material_add'))


class MaterialImportFromView(MaterialAccessMixin, View):
    """编辑页「导入数据」：把来源牌号的数据在事务内替换到当前材料。

    与新增页不同，这里直接落库（对标 app_formula 的 FormulaImportFromView）：
    覆盖标量字段 + 整体替换物性数据行。加工条件 / 应用场景 / 特征属性不受影响。
    """
    permission_required = 'app_material.change_materiallibrary'
    model = MaterialLibrary

    def post(self, request, pk):
        target = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_edit_permission(target)  # 仅创建人 / 超管可改
        back = redirect(reverse('material_edit', kwargs={'pk': target.pk}))

        source_id = request.POST.get('source_material_id')
        if not source_id:
            messages.error(request, '请选择要导入的参考牌号')
            return back
        try:
            source = self.get_queryset().get(pk=source_id)
        except (MaterialLibrary.DoesNotExist, ValueError):
            messages.error(request, '所选参考牌号不存在')
            return back
        self.check_object_permission(source)

        if source.pk == target.pk:
            messages.error(request, '不能把牌号导入到它自身')
            return back

        rows = _material_data_point_rows(source)
        with transaction.atomic():
            target.category = source.category
            for field in IMPORT_SCALAR_FIELDS:
                if field != 'category':
                    setattr(target, field, getattr(source, field))
            target.save(update_fields=IMPORT_SCALAR_FIELDS)

            # 顺序不可颠倒：unique_together ('material', 'test_config') 会让「先建后删」抛 IntegrityError
            target.properties.all().delete()
            # 逐行 create 而非 bulk_create —— 缓存失效挂在 MaterialDataPoint 的
            # post_save 接收器上（app_material/signals.py），bulk_create 会静默绕过它
            for row in rows:
                MaterialDataPoint.objects.create(
                    material=target, **_as_model_kwargs(row))

        messages.success(
            request,
            f'已从牌号「{source.grade_name}」导入 {len(rows)} 条物性数据（原数据已替换），请确认后保存。',
        )
        return back


class MaterialDetailView(MaterialAccessMixin, DetailView):
    """详情展示：全员内部可见。"""
    permission_required = 'app_material.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_detail.html'
    context_object_name = 'material'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'category', 'creator'
        ).prefetch_related(
            'characteristics', 'scenarios'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sorted_properties = self.object.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        context['sorted_properties'] = sorted_properties

        related_projects = self.object.projects.select_related('manager').prefetch_related('nodes').order_by('-created_at')
        context['related_projects'] = related_projects

        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
        
        def get_val_subquery(keyword):
            std_query = Q()
            for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)
            return Subquery(
                FormulaTestResult.objects.filter(std_query, formula=OuterRef('pk'), test_config__name__icontains=keyword).values('value')[:1],
                output_field=DecimalField()
            )

        formulas = LabFormula.objects.filter(project__material=self.object).select_related('creator', 'process').prefetch_related(
            'bom_lines', 'color_powder_bom__entries',
        ).annotate(
            val_density=get_val_subquery('密度'), val_melt=get_val_subquery('熔融'),
            val_tensile=get_val_subquery('拉伸强度'), val_flex_strength=get_val_subquery('弯曲强度'),
            val_flex_modulus=get_val_subquery('弯曲模量'), val_impact=get_val_subquery('冲击'),
            val_hdt=get_val_subquery('热变形'),
        ).order_by('-created_at')

        for f in formulas:
            f.display_props = {
                'density': f.val_density, 'melt': f.val_melt, 'tensile': f.val_tensile,
                'flex_strength': f.val_flex_strength, 'flex_modulus': f.val_flex_modulus,
                'impact': f.val_impact, 'hdt': f.val_hdt,
            }

        from app_raw_material.models import PriceAvgConfig

        # 预热成本计算器：模板逐个读 f.unit_cost，共用一次价格装载
        from app_formula.services import FormulaCostCalculator
        FormulaCostCalculator.for_formulas(formulas)

        context.update({
            'related_formulas': formulas,
            'current_std': current_std,
            'std_tabs': STD_TABS,
            'cart_formula_ids': self.request.session.get('cart_formulas_v2', []),
            'avg_months': PriceAvgConfig.get().months,
        })
        return context


class MaterialBulkPublishView(MaterialAccessMixin, View):
    """批量发布：需具备编辑权限。"""
    permission_required = 'app_material.change_materiallibrary'
    model = MaterialLibrary

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids, action = data.get('ids', []), data.get('action')
            if not ids or action not in ['publish', 'unpublish']:
                return JsonResponse({'status': 'error', 'message': '参数错误'}, status=400)

            is_published = (action == 'publish')
            qs = self.get_queryset()
            objs = list(qs.filter(pk__in=ids))
            # 仅创建人或超管可发布/下架归属材料
            for obj in objs:
                self.check_edit_permission(obj)
            with transaction.atomic():
                updated_count = qs.filter(pk__in=ids).update(is_published=is_published)
                # .update() 不触发 post_save，需手动刷新对外数据缓存
                MaterialCache.invalidate(trigger='MaterialBulkPublishView')

            return JsonResponse({'status': 'success', 'message': f'成功{"发布" if is_published else "下架"} {updated_count} 个牌号'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

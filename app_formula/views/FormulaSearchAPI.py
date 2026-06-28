from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.db.models import Q, Count, Max, Min
from app_formula.models import LabFormula
from app_formula.mixins import FormulaAccessMixin


class FormulaAutocompleteView(FormulaAccessMixin, View):
    """
    配方搜索 API — 受 FormulaAccessMixin 权限管控
    - 角色限制：仅 ENGINEER / ADMIN
    - 数据范围：部门隔离（按 creator 字段过滤）
    """
    permission_required = 'app_formula.view_labformula'
    model = LabFormula

    def get(self, request):
        query = request.GET.get('q', '')
        qs = self.get_queryset()
        qs = qs.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        )

        page = request.GET.get('page')
        if page is not None:
            try:
                page = int(page)
                page_size = int(request.GET.get('page_size', 10))
            except (ValueError, TypeError):
                page = 1
                page_size = 10
            if page < 1:
                page = 1
            total = qs.count()
            offset = (page - 1) * page_size
            results = []
            for item in qs[offset:offset + page_size]:
                results.append({
                    'value': item.pk,
                    'text': f"{item.name} (实验单号: {item.code} | 版本号: v{item.version})",
                    'url': reverse('formula_detail', kwargs={'pk': item.pk}),
                })
            return JsonResponse({
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size,
                'has_next': offset + page_size < total,
                'has_prev': page > 1,
            })

        data = [{
            'value': item.pk,
            'text': f"{item.name} (实验单号: {item.code} | 版本号: v{item.version})",
        } for item in qs[:20]]
        return JsonResponse(data, safe=False)


class ExperimentOrderAutocompleteView(FormulaAccessMixin, View):
    """
    实验单搜索 API — 按 code 去重聚合，返回实验单列表（而非单个配方版本）
    用于「导入数据」功能：选择一个实验单后，将其下所有版本的 BOM 合并导入
    每条结果附带 v1 配方的详情页链接，方便用户在导入前预览。

    查询参数：
    - q: 通用关键词（兼容旧版，搜索 code + name）
    - code: 实验单号前缀匹配（istartswith，可利用索引）
    - name: 配方名称包含匹配（icontains）
    - page/page_size: 分页
    多参数组合时为 AND 逻辑。
    """
    permission_required = 'app_formula.view_labformula'
    model = LabFormula

    def get(self, request):
        query = request.GET.get('q', '')
        qs = self.get_queryset()

        # ── 多字段筛选（AND 组合，各自利用索引） ──
        # 实验单号 — 前缀匹配（可走 B-tree 索引）
        code_val = request.GET.get('code', '').strip()
        if code_val:
            qs = qs.filter(code__istartswith=code_val)

        # 配方名称 — 包含匹配
        name_val = request.GET.get('name', '').strip()
        if name_val:
            qs = qs.filter(name__icontains=name_val)

        # 创建人（实验员）— 精确匹配
        owner_id = request.GET.get('owner_id', '').strip()
        if owner_id:
            qs = qs.filter(creator_id=owner_id)

        # 兼容旧版单一关键词搜索（仅在未使用多字段时单独生效，
        # 若同时提供了 q 和多字段，则 AND 追加）
        if query:
            qs = qs.filter(
                Q(code__icontains=query) | Q(name__icontains=query)
            )

        # 按 code 聚合，获取每个实验单的版本数、最新版本名、版本号范围
        aggregated = qs.values('code').annotate(
            version_count=Count('id'),
            latest_name=Max('name'),  # 用最高版本号对应的名称
            min_version=Min('version'),
            max_version=Max('version'),
        ).order_by('-code')

        def _build_results(rows):
            """将聚合行转为结果列表，批量获取 v1 配方 pk 用于生成详情链接"""
            if not rows:
                return []
            # 批量获取所有实验单的 v1 配方 pk（单次查询）
            code_version_pairs = [(r['code'], r['min_version']) for r in rows]
            from django.db.models import Q as _Q
            v1_filter = _Q()
            for code, min_v in code_version_pairs:
                v1_filter |= _Q(code=code, version=min_v)
            v1_map = {}
            if v1_filter:
                for f in LabFormula.objects.filter(v1_filter).only('pk', 'code', 'version'):
                    v1_map[f.code] = f.pk

            results = []
            for row in rows:
                code = row['code']
                version_count = row['version_count']
                max_v = row['max_version']
                latest_name = row['latest_name'] or ''

                if version_count == 1:
                    version_desc = f'v{max_v}'
                else:
                    version_desc = f"v{row['min_version']}~v{max_v}"

                v1_pk = v1_map.get(code)
                url = reverse('formula_detail', kwargs={'pk': v1_pk}) if v1_pk else ''

                results.append({
                    'value': code,
                    'text': f'{code} — 共{version_count}个版本 ({version_desc}) | 最新: {latest_name}',
                    'version_count': version_count,
                    'latest_name': latest_name,
                    'url': url,
                })
            return results

        page = request.GET.get('page')
        if page is not None:
            try:
                page = int(page)
                page_size = int(request.GET.get('page_size', 8))
            except (ValueError, TypeError):
                page = 1
                page_size = 8
            if page < 1:
                page = 1

            total = aggregated.count()
            offset = (page - 1) * page_size
            results = _build_results(list(aggregated[offset:offset + page_size]))

            return JsonResponse({
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size,
                'has_next': offset + page_size < total,
                'has_prev': page > 1,
            })

        # 无分页时返回前20条
        results = _build_results(list(aggregated[:20]))
        return JsonResponse({'results': results, 'total': len(results)})

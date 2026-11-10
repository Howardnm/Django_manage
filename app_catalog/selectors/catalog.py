"""已发布材料的只读查询。不含缓存，不含响应组装。"""
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch
from django.urls import reverse

from app_attachment.models import Attachment
from app_attachment.registry import get_attachment_config_for_model
from app_material.models.material import (
    ApplicationScenario,
    MaterialCharacteristic,
    MaterialDataPoint,
    MaterialLibrary,
    MaterialType,
)

# 导航背景图的 URL 段 → 维度模型。与 /api/catalog/v1/background/<kind>/<pk>/ 一致
NAV_BACKGROUND_MODELS = {
    'scenario': ApplicationScenario,
    'type': MaterialType,
    'characteristic': MaterialCharacteristic,
}


def published_materials():
    """列表查询集：只取列表要的关联，不拉物性子表。"""
    return (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category')
        .prefetch_related('scenarios', 'characteristics')
    )


def published_material_detail():
    """详情查询集：物性按分类、指标顺序预取。"""
    points = MaterialDataPoint.objects.select_related(
        'test_config', 'test_config__category',
    ).order_by('test_config__category__order', 'test_config__order')
    return (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category', 'processing_condition')
        .prefetch_related(
            'scenarios', 'characteristics',
            Prefetch('properties', queryset=points),
        )
    )


def attachment_for(material, category):
    """取该材料指定类别的未删除附件，没有则 None。

    版本号大的优先；版本相同取上传时间更新的；再相同取主键更大的。
    """
    content_type = ContentType.objects.get_for_model(material)
    return Attachment.objects.filter(
        content_type=content_type,
        object_id=material.pk,
        category=category,
        is_deleted=False,
    ).order_by('-version', '-uploaded_at', '-pk').first()


def _background_ids(model, ids):
    """这批维度里，挂了合格背景图的主键。每个模型只查一次。"""
    if not ids:
        return set()
    content_type = ContentType.objects.get_for_model(model)
    rows = Attachment.objects.filter(
        content_type=content_type,
        object_id__in=ids,
        category='BACKGROUND',
        is_deleted=False,
    )
    config = get_attachment_config_for_model(model)
    allowed = set()
    for row in rows:
        if row.file and (config is None or config.allows_filename(row.file.name)):
            allowed.add(row.object_id)
    return allowed


def _background_path(kind, pk, attached_ids):
    """有图给相对路径，没有给 None。绝对地址由视图按当次请求拼，避免冻进缓存。"""
    if pk not in attached_ids:
        return None
    return reverse('app_catalog:background', kwargs={'kind': kind, 'pk': pk})


def build_nav_tree():
    """场景 → 类型 → 特征，只统计已发布材料。背景图是相对路径或 None。"""
    products = (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category')
        .prefetch_related('scenarios', 'characteristics')
    )
    tree_map = defaultdict(lambda: {'name': '', 'count': 0, 'types': {}})
    scenario_ids = set()
    type_ids = set()
    characteristic_ids = set()
    for product in products:
        type_id, type_name = product.category_id, product.category.name
        type_ids.add(type_id)
        for scenario in product.scenarios.all():
            scenario_ids.add(scenario.id)
            node = tree_map[scenario.id]
            node['name'] = scenario.name
            type_node = node['types'].setdefault(
                type_id, {'name': type_name, 'count': 0, 'characteristics': {}},
            )
            node['count'] += 1
            type_node['count'] += 1
            for characteristic in product.characteristics.all():
                characteristic_ids.add(characteristic.id)
                char_node = type_node['characteristics'].setdefault(
                    characteristic.id, {'name': characteristic.name, 'count': 0},
                )
                char_node['count'] += 1

    scenario_backgrounds = _background_ids(ApplicationScenario, scenario_ids)
    type_backgrounds = _background_ids(MaterialType, type_ids)
    characteristic_backgrounds = _background_ids(MaterialCharacteristic, characteristic_ids)

    result = []
    for scenario_id, info in tree_map.items():
        scenario = {
            'id': scenario_id,
            'name': info['name'],
            'count': info['count'],
            'background': _background_path('scenario', scenario_id, scenario_backgrounds),
            'types': [],
        }
        for type_id, type_info in sorted(info['types'].items()):
            scenario['types'].append({
                'id': type_id,
                'name': type_info['name'],
                'count': type_info['count'],
                'background': _background_path('type', type_id, type_backgrounds),
                'characteristics': [
                    {
                        'id': char_id,
                        'name': char_info['name'],
                        'count': char_info['count'],
                        'background': _background_path(
                            'characteristic', char_id, characteristic_backgrounds,
                        ),
                    }
                    for char_id, char_info in sorted(type_info['characteristics'].items())
                ],
            })
        result.append(scenario)
    return sorted(result, key=lambda item: item['name'])

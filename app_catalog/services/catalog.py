"""目录读服务：缓存已发布列表/详情/导航树，并解析文档与背景图下载。"""
from django.http import Http404
from django.shortcuts import get_object_or_404

from app_attachment.registry import get_attachment_config_for_model
from app_material.services.material_cache import MaterialCache

from app_catalog.selectors import (
    NAV_BACKGROUND_MODELS,
    attachment_for,
    build_nav_tree,
    published_materials,
)

# 下载路径参数 → Attachment.category（RoHS 为大小写混合）
DOWNLOAD_CATEGORY_MAP = {'tds': 'TDS', 'msds': 'MSDS', 'rohs': 'RoHS'}


def query_cache_key(query_params):
    """把 query 规范成稳定缓存键，分页参数也算进去。"""
    parts = []
    for key in sorted(query_params.keys()):
        for value in sorted(query_params.getlist(key)):
            parts.append(f"{key}={value}")
    return '&'.join(parts)


def _with_absolute_backgrounds(tree, request):
    """复制节点再拼绝对地址。缓存里仍是相对路径，换 Host 不会拿到上一次的域名。"""
    result = []
    for scenario in tree:
        node = dict(scenario)
        if node.get('background'):
            node['background'] = request.build_absolute_uri(node['background'])
        types = []
        for type_node in node['types']:
            copied = dict(type_node)
            if copied.get('background'):
                copied['background'] = request.build_absolute_uri(copied['background'])
            copied['characteristics'] = [
                {
                    **char_node,
                    'background': (
                        request.build_absolute_uri(char_node['background'])
                        if char_node.get('background') else None
                    ),
                }
                for char_node in copied['characteristics']
            ]
            types.append(copied)
        node['types'] = types
        result.append(node)
    return result


class CatalogReadService:
    """视图只把已序列化的结果交给这里缓存。"""

    @staticmethod
    def nav_tree(request):
        tree = MaterialCache.get('catalog:nav_tree', build_nav_tree)
        return _with_absolute_backgrounds(tree, request)

    @staticmethod
    def cached_list(query_key, load_fn):
        return MaterialCache.get(f"catalog:list:{query_key}", load_fn)

    @staticmethod
    def cached_detail(pk, load_fn):
        return MaterialCache.get(f"catalog:detail:{pk}", load_fn)

    @staticmethod
    def download_file(material_id, file_type):
        """已发布材料的文档。类别非法、未发布或没有附件时 404。"""
        category = DOWNLOAD_CATEGORY_MAP.get((file_type or '').lower())
        if category is None:
            raise Http404("不支持的文档类型")
        material = get_object_or_404(published_materials(), pk=material_id)
        attachment = attachment_for(material, category)
        if attachment is None or not attachment.file:
            raise Http404("文件不存在")
        return attachment

    @staticmethod
    def background_file(kind, pk):
        """维度上的导航背景图。主数据不存在、没图或后缀不合格时 404。

        不要求该维度当前出现在导航树里：图挂在主数据上，树只决定展不展示。
        """
        model = NAV_BACKGROUND_MODELS.get(kind)
        if model is None:
            raise Http404("不支持的背景图类型")
        parent = get_object_or_404(model, pk=pk)
        attachment = attachment_for(parent, 'BACKGROUND')
        if attachment is None or not attachment.file:
            raise Http404("背景图不存在")
        config = get_attachment_config_for_model(model)
        if config and not config.allows_filename(attachment.file.name):
            raise Http404("背景图不存在")
        return attachment

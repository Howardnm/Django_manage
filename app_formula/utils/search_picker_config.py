"""配方模块的 SearchPickerConfig 工厂方法。"""
from django.urls import reverse
from common_utils.search_picker_config import SearchPickerConfig


def for_formula_import():
    """
    配方「导入数据」场景：从实验单选择来源，表格展示。

    多字段搜索（AND 组合）：
    - 实验单号：前缀匹配（istartswith，可利用 B-tree 索引）
    - 配方名称：包含匹配（icontains）
    - 负责人：  精确匹配（creator_id），通过组织架构树选择人员
    空条件时返回全部实验单列表。
    """
    return SearchPickerConfig(
        modal_id='modal-import-formula',
        modal_title='选择来源实验单',
        search_url=reverse('formula_api_search_experiment'),
        display_mode='table',
        search_mode='multi',
        page_size=8,
        show_detail_button=True,
        confirm_text='确认选择',
        search_fields=[
            {
                'name': 'code',
                'type': 'text',
                'label': '实验单号',
                'placeholder': '输入实验单号（前缀匹配）',
            },
            {
                'name': 'name',
                'type': 'text',
                'label': '配方名称',
                'placeholder': '输入配方名称（包含匹配）',
            },
            {
                'name': 'owner_id',
                'type': 'user',
                'label': '负责人',
                'placeholder': '点击选择负责人',
                'multi': False,
            },
        ],
        table_columns=[
            {'key': 'value', 'title': '实验单号',
             'width': '180px', 'monospace': True},
            {'key': 'latest_name', 'title': '实验单名称'},
            {'key': 'version_count', 'title': '配方版本数量',
             'width': '130px'},
        ],
    )

"""材料成品库的 SearchPickerConfig 工厂方法。"""
from django.urls import reverse

from common_utils.search_picker_config import SearchPickerConfig


def for_material_import():
    """
    成品材料「导入数据」场景：选择一条已有牌号作为复制来源。

    多字段筛选（AND 组合，前端只发非空字段，全空即浏览全部）：
    - 牌号：包含匹配（icontains）
    - 厂家：包含匹配（icontains）
    - 材料类型：精确匹配 category_id，走可搜索的远程下拉

    映射逻辑在 app_material/apps.py 的 _filter_material_import()，
    由 common_autocomplete 接口按 filter_fn 契约调用。

    注意：不能直接用 SearchPickerConfig.for_model_table() —— 它把
    search_mode 固定为 'simple'，此处需要 'multi' 才能渲染筛选字段，
    因此用 for_custom_url() 显式传入全部参数。
    """
    return SearchPickerConfig.for_custom_url(
        modal_id='modal-import-material',
        modal_title='选择参考牌号',
        search_url=reverse('common_autocomplete'),
        display_mode='table',
        search_mode='multi',
        search_model='material_import',
        modal_size='xl',          # 6 列 + 查看按钮，默认宽度放不下
        page_size=8,
        show_detail_button=True,
        confirm_text='确认选择',
        search_fields=[
            {
                'name': 'grade_name',
                'type': 'text',
                'label': '牌号',
                'placeholder': '输入牌号（包含匹配）',
            },
            {
                'name': 'manufacturer',
                'type': 'text',
                'label': '生产基地',
                'placeholder': '输入生产基地（包含匹配）',
            },
            {
                'name': 'category_id',
                'type': 'remote-select',
                'label': '材料类型',
                'model': 'material_type',
                'placeholder': '点击选择材料类型',
            },
        ],
        table_columns=[
            {'key': 'grade_name', 'title': '牌号',
             'width': '150px', 'monospace': True},
            {'key': 'manufacturer', 'title': '生产基地', 'width': '110px'},
            {'key': 'sap_material_code', 'title': 'SAP编码',
             'width': '130px', 'monospace': True},
            {'key': 'characteristics', 'title': '特征属性'},
            {'key': 'scenarios', 'title': '应用场景'},
            {'key': 'material_color_name', 'title': '颜色名称', 'width': '100px'},
        ],
    )

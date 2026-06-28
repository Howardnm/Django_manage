"""
通用搜索选择器配置类。

所有配置从 Python → JSON → JS 流，模板零参数注入。
View 实例化此类 → 模板读取 context['search_picker'] → JS 解析 JSON 初始化。

Exports:
    SearchPickerConfig — 搜索选择器配置数据类
    SearchPickerConfig.for_model_search() — 通用列表搜索工厂
    SearchPickerConfig.for_model_table() — 通用表格搜索工厂
    SearchPickerConfig.for_custom_url() — 自定义 URL 工厂

用法:
    from common_utils import SearchPickerConfig

    config = SearchPickerConfig.for_model_search('my-modal', '选择材料', 'material')
    context['search_picker'] = config
"""

import json
from dataclasses import dataclass, field
from django.urls import reverse


@dataclass
class SearchPickerConfig:
    """
    搜索选择器配置 — 单一配置源。

    字段命名：Python 端 snake_case，to_json() 输出 camelCase 匹配 JS 端。

    multi 模式下的 search_fields 支持 6 种字段类型：
        text          — 普通文本输入
        select        — 本地下拉（TomSelect 本地搜索，需传 options）
        remote-select — 远程单选下拉（TomSelect remote，需传 api_url 或 model）
        remote-multi  — 远程多选下拉（同上，自动 multiple）
        date          — 日期输入（<input type="date">）
        user          — 人员选择器（内部调用 UserPickerWidget overlay，
                        通过 multi: true/false 控制单选/多选）

    用法示例:
        config = SearchPickerConfig.for_model_search(
            modal_id='my-modal', modal_title='选择对象',
            model_type='material', search_mode='multi',
            search_fields=[
                {'name': 'name', 'type': 'text', 'placeholder': '材料名称'},
                {'name': 'category', 'type': 'select',
                 'options': [{'value': 'A', 'text': 'A类'}, {'value': 'B', 'text': 'B类'}]},
                {'name': 'owner', 'type': 'user', 'multi': True},
            ],
        )
    """

    modal_id: str
    modal_title: str
    search_url: str                        # 已解析的 API URL（通过 reverse()）
    display_mode: str = 'list'             # 'list' | 'table'
    search_mode: str = 'simple'            # 'simple' | 'multi'
    placeholder: str = '输入关键词搜索...'
    page_size: int = 8
    show_detail_button: bool = False
    confirm_text: str = '确认选择'
    initial_search: bool = False
    search_model: str = ''                 # 传递给 API 的 model 参数
    table_columns: list = field(default_factory=list)
    # search_fields 子项结构：
    #   {name, type='text'|'select'|'remote-select'|'remote-multi'|'date'|'user',
    #    label?, placeholder?, options?, model?, api_url?, value_field?, response_key?,
    #    multi? (仅 user 类型: True=多选, False=单选)}
    search_fields: list = field(default_factory=list)
    # response_mapping 子项结构（camelCase，直接透传到 JS 端）：
    #   {resultsKey?, totalKey?, pageKey?, pageSizeKey?,
    #    hasNextKey?, hasPrevKey?, valueField?, textField?}
    response_mapping: dict = field(default_factory=dict)

    @property
    def json(self) -> str:
        """
        模板友好访问器：{{ config.json|safe }} 直接输出 JSON。

        键名使用 camelCase 匹配 JS 端 SearchPickerConfig 属性名。
        空列表/字典也输出（JS 端统一处理默认值）。
        """
        return self.to_json()

    def to_json(self) -> str:
        """同上，供非模板场景调用。"""
        data = {
            'searchUrl': self.search_url,
            'searchModel': self.search_model,
            'displayMode': self.display_mode,
            'searchMode': self.search_mode,
            'placeholder': self.placeholder,
            'pageSize': self.page_size,
            'showDetailButton': self.show_detail_button,
            'confirmText': self.confirm_text,
            'initialSearch': self.initial_search,
            'tableColumns': self.table_columns,
            'searchFields': self.search_fields,
        }
        if self.response_mapping:
            data['responseMapping'] = self.response_mapping
        return json.dumps(data, ensure_ascii=False)

    # ── 工厂方法 ──

    @classmethod
    def for_custom_url(cls, modal_id, modal_title, search_url, **kwargs):
        """
        通用工厂 — 接受任意预解析的 URL。

        适用于 app 自有搜索 API（非 common_autocomplete）的场景。
        """
        return cls(modal_id=modal_id, modal_title=modal_title, search_url=search_url, **kwargs)

    @classmethod
    def for_model_search(cls, modal_id, modal_title, model_type, **kwargs):
        """
        通用搜索选择器 — 适配 common_utils MaterialAutocompleteView。

        model_type 对应各业务 app 在 AppConfig.ready() 中通过
        register_autocomplete(key, ...) 注册的字符串键。
        具体可用值取决于各 app 的注册情况，基础设施层不做硬性枚举。

        用法:
            config = SearchPickerConfig.for_model_search(
                modal_id='modal-material-picker',
                modal_title='选择材料',
                model_type='material',
            )
        """
        return cls(
            modal_id=modal_id,
            modal_title=modal_title,
            search_url=reverse('common_autocomplete'),
            search_mode='simple',
            search_model=model_type,
            placeholder=f'输入关键词搜索...',
            page_size=10,
            **kwargs
        )

    @classmethod
    def for_model_table(cls, modal_id, modal_title, model_type, table_columns, **kwargs):
        """
        通用搜索选择器（表格模式） — 带表格列定义。

        model_type 含义同 for_model_search()，对应注册表中的字符串键。

        用法:
            config = SearchPickerConfig.for_model_table(
                modal_id='modal-material-table',
                modal_title='选择材料',
                model_type='material',
                table_columns=[
                    {'key': 'value', 'title': '牌号', 'width': '180px'},
                    {'key': 'text', 'title': '名称'},
                ],
            )
        """
        return cls(
            modal_id=modal_id,
            modal_title=modal_title,
            search_url=reverse('common_autocomplete'),
            display_mode='table',
            search_mode='simple',
            search_model=model_type,
            placeholder='输入关键词搜索...',
            page_size=10,
            table_columns=table_columns,
            show_detail_button=True,
            **kwargs
        )

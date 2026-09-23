"""MCP 工具的 structured output 形状（与 serializer 字段一一对应）。

两条约定：

1. 工具的返回注解一律写成 `XxxOut | ToolErrorOut`（见 app_mcp_server/responses.py）：
   SDK 会为联合类型包一层，最终 structuredContent 是 `{"result": <信封>}`。
2. **空属性一律是 `None`**，类型标成 `| None`；不存在 "N/A" 之类的字符串哨兵。
   字段本身不会因为没值而消失（`business_info` 以前会被 pop 掉，现在给 null）。
"""
from typing import Literal, NotRequired, TypedDict


class AttachmentOut(TypedDict):
    name: str | None
    type: str | None
    version: int
    uploaded_at: str | None


class ProjectListOut(TypedDict):
    id: int
    name: str
    manager: str
    current_stage: str
    progress_percent: int
    is_terminated: bool
    created_at: str | None


class ProjectNodeOut(TypedDict):
    stage: str
    round: int
    status: str
    remark: str | None
    updated_at: str | None


class ProjectBusinessInfo(TypedDict):
    customer: str | None
    oem: str | None
    salesperson: str | None
    product_name: str | None
    target_material: str | None
    target_cost: float | None  # 未设目标成本 → None（0 表示目标成本为零）


class ProjectDetailOut(ProjectListOut):
    timeline: list[ProjectNodeOut]
    # 无业务档案 → None；有档案没附件 → []；读取失败 → None + warnings
    associated_files: list[AttachmentOut] | None
    business_info: ProjectBusinessInfo | None
    # 局部降级说明（例如附件读取失败），有才出现
    warnings: NotRequired[list[str]]


class ProjectSearchOut(TypedDict):
    """搜索类工具的成功信封；零命中或截断时 `hint` 说明原因。"""

    ok: Literal[True]
    data: list[ProjectListOut]
    total: int  # 匹配总数；未传 limit 时等于 returned
    returned: int  # 本次返回条数（= len(data)，显式给出免得 agent 数错）
    has_more: bool  # 只有显式传了 limit 才可能为 True
    hint: NotRequired[str]


class PropertyItem(TypedDict):
    name: str
    name_en: str | None
    value: float | str | None
    unit: str | None
    standard: str
    condition: str | None
    data_type: str
    min_value: float | None
    max_value: float | None
    min_value_text: str | None
    max_value_text: str | None


class PropertyGroup(TypedDict):
    category_name: str
    items: list[PropertyItem]


class MaterialOut(TypedDict):
    id: int
    grade_name: str
    manufacturer: str | None
    category: str
    flammability: str | None
    description: str | None
    # 物性名 → "值 单位"；该物性没有记录值时为 None
    properties_summary: dict[str, str | None]
    grouped_properties: list[PropertyGroup]
    # 读取失败 → None + warnings；确实没有附件 → []
    files: list[AttachmentOut] | None
    created_at: str | None
    # 局部降级说明（例如附件读取失败），有才出现
    warnings: NotRequired[list[str]]


class MaterialSearchOut(TypedDict):
    """搜索类工具的成功信封；零命中或截断时 `hint` 说明原因。"""

    ok: Literal[True]
    data: list[MaterialOut]
    total: int
    returned: int
    has_more: bool
    hint: NotRequired[str]


class FormulaBOMOut(TypedDict):
    raw_material: str
    model: str | None
    category: str
    percentage: float
    feeding_port: str
    weighing_scale: str
    is_pre_mix: bool


class FormulaTestOut(TypedDict):
    item: str
    value: float | str | None
    unit: str | None
    standard: str


class FormulaOut(TypedDict):
    code: str
    version: int
    name: str
    material_type: str
    cost_predicted: float | None  # 实时计算；BOM 任一行缺价时为 None
    bom: list[FormulaBOMOut]
    test_results: list[FormulaTestOut]
    description: str | None
    created_at: str | None
    # 局部提醒（例如存在被隔离的更高版本），有才出现
    warnings: NotRequired[list[str]]


class FormulaSearchOut(TypedDict):
    """搜索类工具的成功信封；零命中或截断时 `hint` 说明原因。"""

    ok: Literal[True]
    data: list[FormulaOut]
    total: int
    returned: int
    has_more: bool
    hint: NotRequired[str]


class MaterialWithFormulasOut(MaterialOut):
    associated_formulas_history: list[FormulaOut]
    # 因权限未返回的条数（L1/L4 隔离或配方模块无权），配合 note 说明
    associated_formulas_total: NotRequired[int]
    associated_formulas_hidden: NotRequired[int]
    associated_formulas_note: NotRequired[str]


# ══════════════════════════════════════════════════════════
#  get_mcp_health 的输出形状（不是业务数据，是注册期/权限的体检报告）
# ══════════════════════════════════════════════════════════


class ToolLoadFailure(TypedDict):
    module: str
    error: str


class ToolRegistryHealth(TypedDict):
    registered: int
    guarded: int
    # 未受保护的工具名：漏套 @safe_tool，或返回注解读不出 output_schema
    unguarded: list[str]
    load_failures: list[ToolLoadFailure]
    duplicate_names: list[str]


class CallerOut(TypedDict):
    username: str
    role: str | None
    level: int
    department: str | None


class ModuleAccessOut(TypedDict):
    module: str
    allowed: bool
    # allowed=False 时说明卡在哪一层；allowed=True 时多为 None
    reason: str | None
    # allowed=True 时的补充（例如数据仍会被部门/工作组隔离）
    note: NotRequired[str]


class HealthOut(TypedDict):
    ok: Literal[True]
    caller: CallerOut
    tools: ToolRegistryHealth
    module_access: list[ModuleAccessOut]

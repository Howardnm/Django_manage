"""MCP 工具的 structured output 形状（与 serializer 字段一一对应）。"""
from typing import NotRequired, TypedDict


class AttachmentOut(TypedDict):
    name: str
    type: str
    version: int
    uploaded_at: str


class ProjectListOut(TypedDict):
    id: int
    name: str
    manager: str
    current_stage: str
    progress_percent: int
    is_terminated: bool
    created_at: str


class ProjectNodeOut(TypedDict):
    stage: str
    round: int
    status: str
    remark: str
    updated_at: str


class ProjectBusinessInfo(TypedDict):
    customer: str
    oem: str
    salesperson: str
    product_name: str
    target_material: str
    target_cost: float


class ProjectDetailOut(ProjectListOut):
    timeline: list[ProjectNodeOut]
    associated_files: list[AttachmentOut]
    business_info: NotRequired[ProjectBusinessInfo]


class PropertyItem(TypedDict):
    name: str
    name_en: str
    value: float | str | None
    unit: str
    standard: str
    condition: str
    data_type: str
    min_value: float | None
    max_value: float | None
    min_value_text: str
    max_value_text: str


class PropertyGroup(TypedDict):
    category_name: str
    items: list[PropertyItem]


class MaterialOut(TypedDict):
    id: int
    grade_name: str
    manufacturer: str
    category: str
    flammability: str
    description: str
    properties_summary: dict[str, str]
    grouped_properties: list[PropertyGroup]
    files: list[AttachmentOut]
    created_at: str


class FormulaBOMOut(TypedDict):
    raw_material: str
    model: str
    category: str
    percentage: float
    feeding_port: str
    weighing_scale: str
    is_pre_mix: bool


class FormulaTestOut(TypedDict):
    item: str
    value: float | str
    unit: str
    standard: str


class FormulaOut(TypedDict):
    code: str
    version: int
    name: str
    material_type: str
    cost_predicted: float
    bom: list[FormulaBOMOut]
    test_results: list[FormulaTestOut]
    description: str
    created_at: str


class MaterialWithFormulasOut(MaterialOut):
    associated_formulas_history: list[FormulaOut]

"""把实验配方的份数映射成 SAP BOM 行，再新建或整表覆盖。

数量口径：用户填的基准数量是公斤，且必须是整数，原样写入 ``bmeng``，不带小数。
组件数量 ``menge = 份数 / 100 × 基准数量(kg) × 1000``，单位固定 ``G``。
色粉与主配方量纲相同，勾选合并时接在主 BOM 后面，不重新归一。
同一 SAP 编码的多行先把份数加总，再换算一次。
包装袋是可选的额外一行：单位 ``PC``，项目类别与原材料行相同，数量按件数原样写入，不换算、不合并。
损耗率 ``AUSCH`` 默认 ``1``，不写小数。BOM 状态 ``STLST`` 默认 ``1``。
"""

from decimal import Decimal, ROUND_HALF_UP

from app_formula.models import ColorPowderBOM, LabFormula
from app_raw_material.models import RawMaterial
from app_sap_services.services.bom import create_bom, update_bom

_QTY = Decimal("0.001")
_SCRAP = Decimal("0.01")
_HUNDRED = Decimal("100")
_GRAMS_PER_KG = Decimal("1000")
_ITEM_CATEGORY = "L"
_UNIT = "G"
_PACKAGING_PREFIX = "K09"
_PACKAGING_UNIT = "PC"
_DEFAULT_STATUS = "1"
_DEFAULT_SCRAP = Decimal("1")


class FinishedBomPublishError(Exception):
    """映射阶段就拒绝，还没调用 SAP。``detail`` 直接给接口正文。"""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def publish_finished_bom(
    *,
    formula_id: int,
    werks: str,
    stlan: str,
    stlal: str,
    bmeng: int,
    datuv,
    stlst: str = _DEFAULT_STATUS,
    stktx: str = "",
    ztext: str = "",
    ausch: Decimal = _DEFAULT_SCRAP,
    merge_color: bool = False,
    packaging_code: str = "",
    packaging_qty: Decimal | None = None,
    mode: str,
) -> dict:
    """``mode`` 为 ``create`` 或 ``update``。物料号取配方所挂成品，不信请求体。

    Raises:
        LabFormula.DoesNotExist: 配方不存在。
        FinishedBomPublishError: 没有成品、没有可提交的行，或缺 SAP 编码。
    """
    formula = _load_formula(formula_id)
    material = formula.project.material if formula.project_id else None
    if material is None or not (material.sap_material_code or "").strip():
        raise FinishedBomPublishError("配方未关联成品材料")

    lines = build_sap_lines(
        formula,
        bmeng=bmeng,
        datuv=datuv.isoformat() if hasattr(datuv, "isoformat") else str(datuv),
        stlst=stlst or "",
        stktx=stktx or "",
        ztext=ztext or "",
        ausch=ausch,
        merge_color=merge_color,
        packaging_code=packaging_code,
        packaging_qty=packaging_qty,
    )
    writer = create_bom if mode == "create" else update_bom
    messages = writer(
        matnr=material.sap_material_code,
        werks=werks,
        stlan=stlan,
        stlal=stlal,
        lines=lines,
    )
    return {
        "matnr": material.sap_material_code,
        "werks": werks,
        "stlan": stlan,
        "stlal": stlal,
        "mode": mode,
        "messages": messages,
    }


def build_sap_lines(
    formula: LabFormula,
    *,
    bmeng: int,
    datuv: str,
    stlst: str,
    stktx: str,
    ztext: str,
    merge_color: bool,
    ausch: Decimal = _DEFAULT_SCRAP,
    packaging_code: str = "",
    packaging_qty: Decimal | None = None,
) -> list[dict]:
    """本地行 → ``create_bom`` / ``update_bom`` 的 ``lines``。"""
    entries = _ordered(formula.bom_lines.all())
    if merge_color:
        color = _color_bom(formula)
        if color is not None:
            entries = entries + _ordered(color.entries.all())

    missing = _missing_names(entries)
    if missing:
        names = "、".join(missing)
        raise FinishedBomPublishError(f"这些原材料没有 SAP 编码：{names}")

    collapsed = _collapse(entries)
    if not collapsed:
        raise FinishedBomPublishError("至少一行")

    base = _base(bmeng)
    rows = []
    for index, (code, percentage) in enumerate(collapsed, start=1):
        rows.append({
            "posnr": f"{index * 10:04d}",
            "postp": _ITEM_CATEGORY,
            "idnrk": code,
            "menge": _qty(percentage / _HUNDRED * bmeng * _GRAMS_PER_KG),
            "meins": _UNIT,
            "bmeng": base,
            "datuv": datuv,
            "stlst": stlst,
            "stktx": stktx,
            "ztext": ztext,
            "ausch": _scrap(ausch),
        })
    _append_packaging(
        rows,
        code=packaging_code,
        qty=packaging_qty,
        base=base,
        datuv=datuv,
        stlst=stlst,
        stktx=stktx,
        ztext=ztext,
        ausch=_scrap(ausch),
    )
    return rows


def _append_packaging(rows, *, code, qty, base, datuv, stlst, stktx, ztext, ausch):
    """配方行之后追加一只包装袋。两个都空则不加。"""
    code = (code or "").strip()
    if not code and qty is None:
        return
    if not code or qty is None:
        raise FinishedBomPublishError("包装袋和数量必须同时填写")
    if qty <= 0:
        raise FinishedBomPublishError("包装袋数量必须大于 0")
    if not code.startswith(_PACKAGING_PREFIX):
        raise FinishedBomPublishError("包装袋编码必须以 K09 开头")
    if not RawMaterial.objects.filter(warehouse_code=code).exists():
        raise FinishedBomPublishError("包装袋不存在")
    rows.append({
        "posnr": f"{(len(rows) + 1) * 10:04d}",
        "postp": _ITEM_CATEGORY,
        "idnrk": code,
        "menge": _qty(qty),
        "meins": _PACKAGING_UNIT,
        "bmeng": base,
        "datuv": datuv,
        "stlst": stlst,
        "stktx": stktx,
        "ztext": ztext,
        "ausch": ausch,
    })


def _load_formula(formula_id: int) -> LabFormula:
    return (
        LabFormula.objects.select_related("project__material")
        .prefetch_related("bom_lines__raw_material", "color_powder_bom__entries__raw_material")
        .get(pk=formula_id)
    )


def _color_bom(formula):
    try:
        return formula.color_powder_bom
    except ColorPowderBOM.DoesNotExist:
        return None


def _ordered(entries) -> list:
    return sorted(entries, key=_sort_key)


def _sort_key(entry):
    raw = entry.raw_material
    category_order = raw.category.order if raw.category_id else 0
    return (entry.feeding_port, entry.weighing_scale, category_order, raw.name, entry.pk or 0)


def _missing_names(entries) -> list[str]:
    names = []
    seen = set()
    for entry in entries:
        raw = entry.raw_material
        if (raw.warehouse_code or "").strip():
            continue
        if raw.pk in seen:
            continue
        seen.add(raw.pk)
        names.append(raw.name)
    return names


def _collapse(entries) -> list[tuple[str, Decimal]]:
    """按 SAP 编码加总份数，保留第一次出现的位置。"""
    buckets: list[tuple[str, Decimal]] = []
    index = {}
    for entry in entries:
        code = entry.raw_material.warehouse_code.strip()
        slot = index.get(code)
        if slot is None:
            index[code] = len(buckets)
            buckets.append((code, entry.percentage))
        else:
            previous = buckets[slot]
            buckets[slot] = (previous[0], previous[1] + entry.percentage)
    return buckets


def _base(value) -> str:
    """SAP 的 BMENG 只收整数，不写小数点。"""
    return str(int(value))


def _qty(value: Decimal) -> str:
    """3 位小数，半进位。与 SAP 数量字段的小数位一致。"""
    return f"{value.quantize(_QTY, rounding=ROUND_HALF_UP):.3f}"


def _scrap(value: Decimal) -> str:
    """BTCI 的 AUSCH。1% 写成 ``1``，不写 ``1.00``。有小数时去掉末尾的 0。"""
    quantized = value.quantize(_SCRAP, rounding=ROUND_HALF_UP)
    return format(quantized, "f").rstrip("0").rstrip(".")

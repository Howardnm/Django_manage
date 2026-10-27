"""
物料主数据只读查询。

只取物料描述。一张 BOM 的组件号不多，按号精确查，不按料号前缀整段拉。
"""

from app_sap_services import sap
from app_sap_services.definitions.material import MaterialQuery


def material_names(codes: list[str]) -> dict[str, str]:
    """每个物料号对应一个 MAKTX。没有行或描述为空时是空字符串。

    不按工厂筛。描述与工厂无关，同一物料会按工厂返回多行，取第一个非空描述。
    全部号查完后关闭当前线程的 SAP 连接，中途失败也关。
    """
    names: dict[str, str] = {}
    try:
        for code in codes:
            rows = sap.rfc(MaterialQuery).filter(mat_range__eq=code).select("MATNR", "MAKTX").call()
            names[code] = _first_maktx(rows, code)
    finally:
        sap.close()
    return names


def _first_maktx(rows, code: str) -> str:
    """只要这次精确查询里、物料号一致的行。空描述跳过。"""
    for row in rows:
        matnr = (getattr(row, "MATNR", "") or "").strip()
        if matnr != code:
            continue
        text = (getattr(row, "MAKTX", "") or "").strip()
        if text:
            return text
    return ""

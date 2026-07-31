"""
原材料库存 RFC 函数声明式定义。

当前已定义:
    MaterialStockQuery  — 物料批次库存查询 (ZRFC_GET_MAT_STOCK)
"""

from ..schemas import (
    RfcSchema,
    RangeTableParam,
    OutputTable,
    CharField,
    DecimalField,
)

from ..converters import clean_leading_zeros


class MaterialStockQuery(RfcSchema):
    """
    物料批次库存查询 (ZRFC_GET_MAT_STOCK)。

    查询物料在各工厂的库存快照，按库位和批次分组。

    SAP 接口文档: ZRFC_GET_MAT_STOCK
    - Tables:  MAT_RANGE, WEK_RANGE, LGO_RANGE, CHA_RANGE (RANGE 结构)
    - Output:  IT_ITEM (ZWMSMCHB 结构)

    字段语义:
        CLABS (LABST) — 非限制使用库存，实际可用量，可直接用于生产领料
        EISBE (EISBE) — 安全库存阈值，MRP 参数，低于此值触发补货建议（非实际库存）

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.stock import MaterialStockQuery

        # 查询全部库存
        result = sap.rfc(MaterialStockQuery).collect()

        # 按物料筛选
        result = sap.rfc(MaterialStockQuery) \
            .filter(mat_range__cp="A01*") \
            .filter(wek_range__eq="3011") \
            .call()

        for row in result:
            print(f"{row.MATNR} [{row.WERKS}] {row.LGORT}/{row.CHARG}: "
                  f"CLABS={row.CLABS}, EISBE={row.EISBE}")
    """

    function_name = "ZRFC_GET_MAT_STOCK"

    # ---- 输入参数 (Range Tables) ----
    mat_range = RangeTableParam("MAT_RANGE", field="MATNR")      # 物料编号查询条件
    wek_range = RangeTableParam("WEK_RANGE", field="WERKS")      # 工厂查询条件
    lgo_range = RangeTableParam("LGO_RANGE", field="LGORT")      # 库存地点查询条件（暂弃用）
    cha_range = RangeTableParam("CHA_RANGE", field="CHARG")      # 批次查询条件（暂弃用）

    # ---- 输出表 ----
    class IT_ITEM(OutputTable):
        MATNR = CharField("物料编号", converter=clean_leading_zeros)
        MAKTX = CharField("物料描述")
        WERKS = CharField("工厂")
        LGORT = CharField("库存地点")
        CHARG = CharField("批号")
        CLABS = DecimalField("非限制库存", decimals=3)
        EISBE = DecimalField("安全库存", decimals=3)
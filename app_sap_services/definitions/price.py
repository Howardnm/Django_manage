"""
物料价格 RFC 函数声明式定义。

后期添加新价格 RFC 时，参考此文件的声明模式:
  1. 继承 RfcSchema
  2. 设置 function_name
  3. 声明 ImportParam / RangeTableParam 参数
  4. 声明 OutputTable 内嵌类描述输出字段

当前已定义:
    MaterialPriceQuery  — 物料评估价格 (ZRFC_GET_MBEW)

待添加 (需SAP授权):
    # MaterialInvoicePriceQuery  — 最新开票价格 (ZRFC_GET_LAST_INVOICE_PRICE)
"""

from ..schemas import (
    RfcSchema,
    RangeTableParam,
    ImportParam,
    OutputTable,
    CharField,
    IntField,
    DecimalField,
)

from ..converters import clean_leading_zeros


class MaterialPriceQuery(RfcSchema):
    """
    物料评估价格查询 (ZRFC_GET_MBEW)。

    按会计年度/期间查询物料评估价格（移动平均价/标准价）。

    SAP 接口文档: ZRFC_GET_MBEW (#13)
    - Import:  P_LFGJA (会计年度), P_LFMON (会计期间)
    - Tables:  S_BWKEY (评估范围 range)
    - Export:  E_RTYPE (消息类型), E_RTMSG (消息文本)
    - Output:  IT_ITEM (MBEW 结构)

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.price import MaterialPriceQuery

        # 查询单月价格
        result = sap.rfc(MaterialPriceQuery) \
            .filter(p_lfgja="2026", p_lfmon="07") \
            .filter(s_bwkey__eq="1010") \
            .call()

        # 快捷调用
        result = sap.call(MaterialPriceQuery, p_lfgja="2026", p_lfmon="07")

        for row in result:
            unit_price = row.VERPR / row.PEINH if row.PEINH else None
            print(f"{row.MATNR}: {unit_price} CNY/kg")

    注意:
        - 当前 SAP 账号可能无此 RFC 授权，需联系管理员开通。
        - VERPR 为移动平均价/标准价，PEINH 为价格单位（如 1=每kg, 1000=每吨）。
        - 实际单价 = VERPR / PEINH（由同步命令处理）。
    """

    function_name = "ZRFC_GET_MBEW"

    # ---- Import 标量参数 ----
    p_lfgja = ImportParam("P_LFGJA")   # 会计年度，如 "2026"
    p_lfmon = ImportParam("P_LFMON")    # 会计期间，如 "07"

    # ---- Tables 输入参数 ----
    s_bwkey = RangeTableParam("S_BWKEY", field="BWKEY")

    # ---- 输出表 ----
    class IT_ITEM(OutputTable):
        MATNR = CharField("物料编号", converter=clean_leading_zeros)
        BWKEY = CharField("评估范围/工厂")
        VPRSV = CharField("价格控制标识")           # S=标准价, V=移动平均价
        VERPR = DecimalField("移动平均价格/标准价", decimals=2)
        PEINH = IntField("价格单位")                # 1=每1单位, 1000=每1000单位
        LFGJA = CharField("会计年度")
        LFMON = CharField("会计期间")

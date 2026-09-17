"""
物料价格 RFC 函数声明式定义。

后期添加新价格 RFC 时，参考此文件的声明模式:
  1. 继承 RfcSchema
  2. 设置 function_name
  3. 声明 ImportParam / RangeTableParam 参数
  4. 声明 OutputTable 内嵌类描述输出字段

当前已定义:
    MaterialPriceQuery  — 物料评估价格历史 (ZRFC_GET_MBEWH)

历史沿革 —— 为什么换接口:
    ZRFC_GET_MBEW  （旧）入参 P_LFGJA/P_LFMON，只能查指定单月；传入历史月份
                        时 SAP 返回空数据集，导致历史价格无法回填。
    ZRFC_GET_MBEWH （新）无任何期间入参，一次返回全部历史月份，每行自带
                        BDATJ（会计年度）+ POPER（会计期间）；并新增了服务端
                        物料筛选 S_MATNR。期间筛选相应下移到客户端。

待添加 (需SAP授权):
    # MaterialInvoicePriceQuery  — 最新开票价格 (ZRFC_GET_LAST_INVOICE_PRICE)
"""

from ..schemas import (
    RfcSchema,
    RangeTableParam,
    OutputTable,
    CharField,
    IntField,
    DecimalField,
)

from ..converters import clean_leading_zeros


class MaterialPriceQuery(RfcSchema):
    """
    物料评估价格历史查询 (ZRFC_GET_MBEWH)。

    一次返回全部历史月份的评估价格，没有会计期间入参 —— 期间筛选由调用方
    在客户端做（见 management/commands/sync_material_prices.py）。

    SAP 接口文档: ZRFC_GET_MBEWH
    - Import:  IS_QUERY (ZSD_QUERY_MBEWH 结构)
                 ├─ S_MATNR  range, LOW/HIGH 为 MATNR (CHAR40)
                 └─ S_BWKEY  range, LOW/HIGH 为 EWERK (CHAR4, 工厂/评估范围)
    - Export:  E_RTYPE (消息类型), E_RTMSG (消息文本)
    - Tables:  IT_ITEM (ZFICO_MBEWH, 13 字段)

    IT_ITEM 字段语义:
        BDATJ / POPER   会计年度 / 会计期间 —— 价格归属期间，不是过账日期
        PEINH           价格单位，实际单价 = VERPR / PEINH
        VPRSV           价格控制指示符：S=标准价, V=移动平均价
        VERPR           移动平均价 / 周期单价
        STPRS / PVPRS   标准价 / 周期单位价
        WAERS           货币码
        SALK3 / SALKV   估价的总库存价值 / 基于定期单位价格的评估
        KALNR           成本估算编号
        MATNR / BWKEY   物料编号 / 评估范围（工厂）

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.price import MaterialPriceQuery

        # 单个工厂的全部历史（期间筛选在 Polars 端做）
        df = sap.rfc(MaterialPriceQuery).filter(s_bwkey__eq="1010").collect()

        # 服务端按物料筛选 —— S_MATNR 虽嵌在 IS_QUERY 结构内，
        # 但筛选语法与顶层 range 完全一致
        df = (sap.rfc(MaterialPriceQuery)
                .filter(s_bwkey__eq="1010", s_matnr__cp="A01*")
                .collect())

        # 逐行访问
        for row in sap.rfc(MaterialPriceQuery).filter(s_matnr__eq="A01005000057").call():
            unit_price = row.VERPR / row.PEINH if row.PEINH else None
            print(f"{row.MATNR} {row.BDATJ}-{row.POPER:02d}: {unit_price} {row.WAERS}/kg")

    注意:
        - 实测（工厂 3011 / 2639 行抽样）STPRS 与 PVPRS 恒为 0，只有 VERPR 有值，
          因此单价口径固定用 VERPR / PEINH；PEINH 实测取值为 1 和 10000，除法不可省。
        - MBEWH 只在估值发生变化时记行，数据是稀疏的 —— 某些物料只有少数几个
          期间的记录，缺月属 SAP 语义而非同步失败。
        - S_MATNR 的 LOW/HIGH 是 CHAR40，实测返回的 MATNR 无前导零、无补位，
          clean_leading_zeros 可安全对齐 RawMaterial.warehouse_code。
    """

    function_name = "ZRFC_GET_MBEWH"

    # ---- 消息检查：SAP 返回 E/A 级消息时抛 SAPBusinessError ----
    # 不加这个检查，SAP 的业务错误会被上层当成「查询结果为空」而静默吞掉。
    msg_type_field = "E_RTYPE"
    msg_text_field = "E_RTMSG"

    # 实测该 RFC 用 E_RTYPE='E' + '未查询到相关数据' 表达「该物料/工厂没有价格
    # 记录」，与 S + '查询成功' 严格对应有无数据。逐物料查询时约 6~10% 命中，
    # 属正常空结果；若当错误处理会让整个同步被一个没价格的物料打断。
    # 用精确匹配而非包含匹配：宁可漏配（退化为抛异常，响亮可诊断）也不要
    # 误配（把真实错误当空结果，静默跳过物料）。两种措辞都列上以防 SAP 改文案。
    msg_empty_texts = ("未查询到相关数据", "未查询到数据")

    # ---- 服务端筛选：两个 range 嵌套在 IS_QUERY (ZSD_QUERY_MBEWH) 结构内 ----
    s_matnr = RangeTableParam("S_MATNR", field="MATNR", structure="IS_QUERY")
    s_bwkey = RangeTableParam("S_BWKEY", field="BWKEY", structure="IS_QUERY")

    # ---- 输出表（字段顺序与 SAP 定义一致，便于比对原始返回）----
    class IT_ITEM(OutputTable):
        KALNR = CharField("成本估算编号")                              # NUMC12，标识符，保留原串
        BDATJ = IntField("会计年度")                                   # NUMC4  → 2026
        POPER = IntField("会计期间")                                   # NUMC3  → "009" → 9
        PEINH = IntField("价格单位")                                   # DEC(3,0) → 1 / 10000
        VPRSV = CharField("价格控制指示符")                             # S=标准价, V=移动平均价
        STPRS = DecimalField("标准价格", decimals=2)                    # 实测恒为 0
        PVPRS = DecimalField("周期单位价格", decimals=2)                 # 实测恒为 0
        WAERS = CharField("货币码")                                    # 实测恒为 CNY
        SALK3 = DecimalField("估价的总库存价值", decimals=2)
        SALKV = DecimalField("基于定期单位价格的评估", decimals=2)
        MATNR = CharField("物料编号", converter=clean_leading_zeros)     # CHAR40
        BWKEY = CharField("评估范围/工厂")                              # CHAR4
        VERPR = DecimalField("移动平均价格/周期单价", decimals=2)         # 唯一有值的价格字段

"""
供应商 RFC 函数声明式定义。

参考 price.py 的声明模式:
  1. 继承 RfcSchema
  2. 设置 function_name
  3. 声明 ImportParam 参数
  4. 声明 OutputTable 内嵌类描述输出结构

当前已定义:
    VendorCheckQuery  — 供应商校验 (ZFG_CHECK_VENDOR)
"""

from ..schemas import (
    RfcSchema,
    ImportParam,
    OutputTable,
    CharField,
    IntField,
    DecimalField,
    DateField,
)

from ..converters import clean_leading_zeros


class VendorCheckQuery(RfcSchema):
    """
    供应商校验 (ZFG_CHECK_VENDOR)。

    按供应商帐号（可配合采购组织/公司代码/简称）查询供应商主数据是否存在。

    SAP 接口文档: ZFG_CHECK_VENDOR (#校验供应商)
    - Import:  I_VENDOR (供应商帐号), I_PUR_ORG (采购组织),
               I_COMP_CODE (公司代码), I_SORTL (简称)
    - Export:  ES_LFA1 (供应商主数据-一般), ES_LFM1 (采购组织层),
               ES_LFB1 (公司代码层)
    - Tables:  ET_RETURN (BAPIRET2 返回消息)

    注意:
        - 本函数返回「单结构 Export + 返回表」，请用 sap.call_structured() 调用，
          不要用 sap.rfc().call()（后者假定首个输出表是 list，会报错）。
        - 若 ES_* 结构为空，说明该供应商不存在，可通过 result["ET_RETURN"] 的
          消息判断具体原因。

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.vendor import VendorCheckQuery

        result = sap.call_structured(
            VendorCheckQuery,
            i_vendor="0000203100", i_pur_org="1000", i_comp_code="1000",
        )
        lfa1 = result["ES_LFA1"]      # 类型化单结构 (OutputRecord) 或 None
        lfm1 = result["ES_LFM1"]
        lfb1 = result["ES_LFB1"]
        msgs = result["ET_RETURN"]    # 返回消息列表
        if lfa1:
            print(lfa1.LIFNR, lfa1.NAME1, lfa1.LAND1)
    """

    function_name = "ZFG_CHECK_VENDOR"

    # ---- Import 标量参数 ----
    i_vendor    = ImportParam("I_VENDOR")     # 供应商或债权人帐号 (LIFNR)
    i_pur_org   = ImportParam("I_PUR_ORG")    # 采购组织 (EKORG)
    i_comp_code = ImportParam("I_COMP_CODE")  # 公司代码 (BUKRS)
    i_sortl     = ImportParam("I_SORTL")      # 简称 (SORTL)

    # ---- Export 单结构: 供应商主数据 (一般地区) ----
    class ES_LFA1(OutputTable):
        MANDT = CharField("集团")
        LIFNR = CharField("供应商或债权人的帐号", converter=clean_leading_zeros)
        LAND1 = CharField("国家/地区代码")
        NAME1 = CharField("名称 1")
        NAME2 = CharField("名称 2")
        NAME3 = CharField("名称 3")
        NAME4 = CharField("名称 4")
        ORT01 = CharField("城市")
        ORT02 = CharField("地区")
        PSTLZ = CharField("邮政编码")
        REGIO = CharField("地区（省/州）")
        SORTL = CharField("排序字段")
        STRAS = CharField("街道和房屋号")
        MCOD1 = CharField("匹配码搜索条件 1")
        ANRED = CharField("标题")
        KUNNR = CharField("客户编号", converter=clean_leading_zeros)
        KTOKK = CharField("供应商帐户组")
        BRSCH = CharField("行业代码")
        LOEVM = CharField("主记录的集中删除标志")
        SPERR = CharField("中心记帐冻结")
        SPERM = CharField("中心施加的采购冻结")
        SPERZ = CharField("付款冻结")
        SPRAS = CharField("语言代码")
        STCD1 = CharField("税号 1")
        STCD2 = CharField("税号 2")
        STCEG = CharField("增值税登记号")
        TXJCD = CharField("地区税务代码")
        TELF1 = CharField("第一个电话号")
        TELF2 = CharField("第二个电话号")
        TELFX = CharField("传真号")
        TELBX = CharField("电子信箱号")
        ERDAT = DateField("记录创建日期")
        ERNAM = CharField("创建对象的人员名称")
        AEDAT = DateField("最后更改日期")

    # ---- Export 单结构: 供应商主数据 (采购组织层) ----
    class ES_LFM1(OutputTable):
        MANDT = CharField("集团")
        LIFNR = CharField("供应商帐户号", converter=clean_leading_zeros)
        EKORG = CharField("采购组织")
        ERDAT = DateField("记录的创建日期")
        ERNAM = CharField("对象创建者的名称")
        SPERM = CharField("采购冻结在采购组织层")
        LOEVM = CharField("采购级别的供应商的删除标记")
        LFABC = CharField("ABC标识")
        WAERS = CharField("采购订单货币")
        VERKF = CharField("供应商办公室的负责销售人员")
        TELF1 = CharField("供应商电话号码")
        MINBW = DecimalField("最小订单值", decimals=2)
        ZTERM = CharField("付款条件代码")
        INCO1 = CharField("国际贸易术语解释通则（部分 1）")
        INCO2 = CharField("国际贸易术语解释通则（部分 2）")
        WEBRE = CharField("基于收货的发票验证")
        KALSK = CharField("计算方案组（供应商）")
        KZAUT = CharField("自动产生允许的采购订单")
        EKGRP = CharField("采购组")
        XERSY = CharField("评估收据结算 (ERS)")
        PLIFZ = IntField("计划交货时间以天计")
        MRPPP = CharField("计划日历")
        LFRHY = CharField("计划周期")
        EIKTO = CharField("我们在供应商处的科目编号")
        VSBED = CharField("装运条件")
        NRGEW = CharField("是否高兴给予折扣的标识符")

    # ---- Export 单结构: 供应商主数据 (公司代码层) ----
    class ES_LFB1(OutputTable):
        MANDT = CharField("集团")
        LIFNR = CharField("供应商或债权人的帐号", converter=clean_leading_zeros)
        BUKRS = CharField("公司代码")
        ERDAT = DateField("记录创建日期")
        ERNAM = CharField("创建对象的人员名称")
        SPERR = CharField("对公司代码过帐冻结")
        LOEVM = CharField("主记录删除标记(公司代码级)")
        ZUAWA = CharField("根据分配号排序代码")
        AKONT = CharField("总帐中的统驭科目")
        BEGRU = CharField("权限组")
        VZSKZ = CharField("利息计算标志")
        ZWELS = CharField("考虑的付款方式清单")
        ZTERM = CharField("付款条件代码")
        EIKTO = CharField("我们带有供应商的帐目号")
        ZSABE = CharField("供应商处的职员")
        KVERM = CharField("备注")
        FDGRV = CharField("计划组")
        LNRZE = CharField("总部帐号")
        LNRZB = CharField("代理收款人帐号")
        XDEZV = CharField("是否本地处理")
        HBKID = CharField("开户银行的简要键")

    # ---- Tables: 返回消息 (BAPIRET2) ----
    class ET_RETURN(OutputTable):
        TYPE = CharField("消息类型: S/E/W/I/A")
        ID = CharField("消息类")
        NUMBER = IntField("消息编号")
        MESSAGE = CharField("消息文本")
        LOG_NO = CharField("应用程序日志: 日志号")
        LOG_MSG_NO = IntField("应用日志: 内部邮件序列号")
        MESSAGE_V1 = CharField("消息变量")
        MESSAGE_V2 = CharField("消息变量")
        MESSAGE_V3 = CharField("消息变量")
        MESSAGE_V4 = CharField("消息变量")
        PARAMETER = CharField("参数名称")
        ROW = IntField("参数中的行")
        FIELD = CharField("参数中的字段")
        SYSTEM = CharField("引发消息的逻辑系统")
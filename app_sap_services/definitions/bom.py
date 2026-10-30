"""
成品材料 BOM RFC 函数声明式定义。

当前已定义:
    MaterialBomQuery      — 读取物料 BOM (ZRFC_GET_MATERIAL_BOM)
    MaterialBomMaintain   — 新建/修改物料 BOM (ZRFC_BOM_CREATE_FOR_PLM)
    MaterialBomLinkQuery  — BOM 表关系链 (ZFG_GET_MAST)
    MaterialBomDelete     — 删除物料 BOM (ZRFC_DELETE_MATERIAL_BOM)
"""

from ..schemas import (
    RfcSchema,
    ImportParam,
    TableInput,
    RangeTableParam,
    OutputTable,
    Field,
    CharField,
    IntField,
    DecimalField,
    DateField,
)

from ..converters import clean_leading_zeros


class MaterialBomQuery(RfcSchema):
    """
    读取物料 BOM (ZRFC_GET_MATERIAL_BOM)。

    按物料、工厂、可选 BOM、有效起始日期展开 BOM，返回 GT_STB（STPOX）。

    SAP 接口:
        - Import: I_MATNR, I_WERKS, I_STALT, I_DATUV, I_EMENG
        - Export: E_RTYPE, E_RTMSG（文档未列，实测存在）
        - Tables: GT_STB

    实测（2026-10-15，物料 A02006000027 / A02006000028，工厂 3011）:
        - I_DATUV 必须是 YYYYMMDD 字符串。不传得到 0 行。
          date 的 str() 是 YYYY-MM-DD，SAP 不认。
        - I_EMENG 必须是 decimal.Decimal。传 int 时 pyrfc 报
          "a decimal value required"。不传仍能返回行。
        - 不存在的 I_STALT（如 02、99）不会报错，会静默退回已有备选。
          不能靠「有行」判断备选存在，要看行上的 STLAL。
        - 物料不存在或工厂没有 BOM 时 E_RTYPE / E_RTMSG 仍是空串，
          GT_STB 为空表。空结果不是 E 文本，所以不设 msg_empty_texts。
        - 同一 POSNR 可以有多行替代料（ALPGR + EWAHR），本接口不折叠。
        - 物料号按库里的值传，不去前导零、也不补位。

    使用示例:
        from decimal import Decimal
        from app_sap_services import sap
        from app_sap_services.definitions.bom import MaterialBomQuery

        rows = sap.rfc(MaterialBomQuery).filter(
            i_matnr="A02006000027",
            i_werks="3011",
            i_stalt="01",
            i_datuv="20261015",
            i_emeng=Decimal("1000"),
        ).call()
        for row in rows:
            print(row.STLAL, row.POSNR, row.IDNRK, row.ALPGR, row.MENGE, row.MEINS)
    """

    function_name = "ZRFC_GET_MATERIAL_BOM"

    # 实测成功和查无数据都是空串。声明后，将来若返回 E/A 会抛 SAPBusinessError，
    # 避免把业务错误当成空 BOM。空串本身不抛错。
    msg_type_field = "E_RTYPE"
    msg_text_field = "E_RTMSG"

    # ---- Import 标量参数（不填默认值；未传入的不进参数字典）----
    i_matnr = ImportParam("I_MATNR")   # 物料编号
    i_werks = ImportParam("I_WERKS")   # 工厂
    i_stalt = ImportParam("I_STALT")   # 可选 BOM，如 "01"
    i_datuv = ImportParam("I_DATUV")   # 有效起始日期，YYYYMMDD
    i_emeng = ImportParam("I_EMENG")   # 基本数量，decimal.Decimal

    # ---- 输出表 GT_STB（STPOX，列顺序与实测返回一致）----
    class GT_STB(OutputTable):
        # 层次 / 抬头
        STUFE = IntField("层次（在多层 BOM 展开中）")
        WEGXX = IntField("路线 (前趋)")
        BMTYP = CharField("物料清单类别")
        TTIDX = IntField("在类别表内的索引")
        VWEGX = IntField("路径（用于多层 BOM 分解）")
        OJTXB = CharField("对象描述(部件)")
        BAUSF = DecimalField("装配报废已经使用(以百分比)", decimals=2)
        STLAN = CharField("BOM 用途")
        STLAL = CharField("可选的 BOM")
        ALTST = CharField("标识：备选")
        VARST = CharField("指示符 : 变式")
        KBAUS = CharField("指示符：可配置 BOM")
        LOEKZ = CharField("删除标识(抬头)")
        OJTXP = CharField("对象描述（项目）")

        # 物料与价格
        MTART = CharField("物料类型")
        WERKS = CharField("工厂")
        VERID = CharField("生产版本")
        VPSTA = CharField("维护全部物料状态")
        FSTAT = CharField("维护状态")
        MMEIN = CharField("基本计量单位")
        BWTTY = CharField("评估类别")
        VPRSV = CharField("价格控制指示符")
        STPRS = DecimalField("标准价格", decimals=2)
        VERPR = DecimalField("移动平均价格/周期单价", decimals=2)
        PREIH = IntField("价格单位(组件物料)")
        SBDKZ = CharField("对于独立和集中需求的相关需求标识")
        XCHAR = CharField("批量管理标识(内部)")
        KZECH = CharField("在生产/处理订单中批量输入的确定")
        KZWSM = CharField("计量单位使用")
        MMSTA = CharField("工厂特定的物料状态")
        MMSTD = DateField("工厂特定物料状态有效的起始日期")
        MSTAE = CharField("跨工厂物料状态")
        MSTDE = DateField("从跨工厂物料状态有效起的日期")
        ZEINR = CharField("文档号码(无文档管理系统)")
        ZEIVR = CharField("文档版本（无文档管理系统）")
        ZEIAR = CharField("凭证类型(无凭证管理系统)")
        ZEIFO = CharField("文件的页面大小（不包括文件管理系统）")
        BLATT = CharField("凭证的页号(不带凭证管理系统)")
        BLANZ = CharField("页数(没有凭证管理系统)")
        DISST = CharField("低层代码")
        DISMM = CharField("物料需求计划类型")
        SERNP = CharField("序列号参数文件")
        MNGLG = DecimalField("以基本计量单位为准的已计算的组件数量", decimals=3)
        MNGKO = DecimalField("以组件计量单位为准的已计算的组件数量", decimals=3)
        MSIGN = CharField("+/- 符号")
        AUSSS = DecimalField("装配报废 (组件物料)", decimals=2)
        KAUSF = DecimalField("组件报废(组件物料)", decimals=2)
        SOBSL = CharField("特殊采购类型")
        SOBSK = CharField("成本核算的特殊采购类型")
        KZAUS = CharField("中止指示符")
        AUSDT = DateField("中断日期")
        NFMAT = CharField("后续物料", converter=clean_leading_zeros)
        RGEKZ = CharField("标识：反冲")
        KZDKZ = CharField("凭证需求标识")
        UMREZ = IntField("基本计量单位转换分子")
        UMREN = IntField("转换为基本计量单位的分母")
        LGPRO = CharField("发货存储地点")
        PRCTR = CharField("利润中心")
        REVLV = CharField("版次")
        KZEFF = CharField("指定有效参数值/覆盖更改编号")
        KZKFG = CharField("可配置物料")
        MCUOB = CharField("配置(物料变式)")
        CUOBJ = CharField("配置(内部对象号)")
        NCONF = CharField("多层上已配置的")
        FBSKZ = CharField("指示符 : 外部采购")
        STAWN = CharField("商品代码")
        PREFE = CharField("进/出口中优惠标识")
        MSCHG = CharField("标识:散装物料(组件物料)")
        FXPRU = CharField("固定价格联产品")
        MATMK = CharField("物料组")
        STABK = CharField("文档状态(语言-相关的)")
        DOSTX = CharField("文档状态描述")

        # 组件行
        STLTY = CharField("物料清单类别")
        STLNR = CharField("物料单")
        STLKN = CharField("BOM 项目节点号")
        STPOZ = CharField("内部计数器")
        STVKN = CharField("BOM 项目的继承节点号")
        DATUV = DateField("有效开始日期/有效截止日期")
        TECHV = CharField("技术状态从")
        AENNR = CharField("变更编号")
        ANDAT = DateField("日期记录创建于")
        ANNAM = CharField("创建记录的用户")
        AEDAT = DateField("最后更改日期")
        AENAM = CharField("更改对象用户的名称")
        IDNRK = CharField("BOM 组件", converter=clean_leading_zeros)
        PSWRK = CharField("发放工厂")
        POSTP = CharField("项目类别")
        POSNR = CharField("BOM 项目号")
        SORTF = CharField("排序字符串")
        MEINS = CharField("组件计量单位")
        MENGE = DecimalField("组件数量", decimals=3)
        FMENG = CharField("固定数量")
        AUSCH = DecimalField("组件报废 (组件)", decimals=2)
        AVOAU = DecimalField("工序报废", decimals=2)
        NETAU = CharField("标志：净废品")
        SCHGT = CharField("指示符：散装物料")
        BEIKZ = CharField("物料供应标识符")
        ERSKZ = CharField("标识：备件")
        RVREL = CharField("标识：与销售相关的项目")
        SANFE = CharField("标识：与生产相关项目")
        SANIN = CharField("指示器：与工厂维护相关的项目")
        SANKA = CharField("与成本核算相关标志")
        SANKO = CharField("标识：与工程相关项目")
        SANVS = CharField("指示器:高级配置")
        STKKZ = CharField("PM 装配指示符")
        REKRI = CharField("标志: BOM 是递归的")
        REKRS = CharField("标志: 递归性允许")
        CADPO = CharField("CAD 标识")
        NLFZT = IntField("提前期偏置量")
        NLFZV = IntField("工序的提前期偏移量")
        NLFMV = CharField("工序提前期偏移量的单位")
        VERTI = CharField("组件消耗的分配键值")
        ALPOS = CharField("指示符：替代项目")
        EWAHR = IntField("使用可能性按 % (可选项目)")
        EKGRP = CharField("采购组")
        LIFZT = IntField("以天计算的交货时间")
        LIFNR = CharField("供应商或债权人的帐号", converter=clean_leading_zeros)
        PREIS = DecimalField("价格", decimals=2)
        PEINH = IntField("价格单位")
        WAERS = CharField("货币码")
        SAKTO = CharField("成本要素")
        ROANZ = DecimalField("可变大小项目号", decimals=3)
        ROMS1 = DecimalField("尺寸1", decimals=3)
        ROMS2 = DecimalField("尺寸2", decimals=3)
        ROMS3 = DecimalField("大小 3", decimals=3)
        ROMEI = CharField("大小 1 到 3 的计量单位")
        ROMEN = DecimalField("可变尺寸项目数量", decimals=3)
        RFORM = CharField("公式码")
        UPSKZ = CharField("指示符 : 子项目存在")

        # 文本与文档
        LTXSP = CharField("语言：用此语言存储长文本")
        POTX1 = CharField("BOM 项目文本（行1）")
        POTX2 = CharField("BOM 项目文本 （行 2）")
        OBJTY = CharField("对象类型（BOM 项目）")
        ITMMK = CharField("物料组")
        WEBAZ = IntField("以天计的收货处理时间")
        DOKAR = CharField("文档类型")
        DOKNR = CharField("凭证编号")
        DOKVR = CharField("文档版本")
        DOKTL = CharField("凭证部分")
        CSSTR = DecimalField("平均物料纯度按 %", decimals=2)
        CLASS = CharField("类号")
        KLART = CharField("类别种类")
        INTRM = CharField("中间物料", converter=clean_leading_zeros)
        POTPR = CharField("项目类别（物料单）")
        EKORG = CharField("采购组织")
        CLOBK = CharField("所需组件")
        CLMUL = CharField("允许的多重选择")
        CVIEW = CharField("组织范围")
        KNOBJ = CharField("具有分配相关性的对象编号")
        LGORT = CharField("库存地点")
        PRVBE = CharField("产品供应范围")
        KZKUP = CharField("指示符：联合产品")
        DATUB = DateField("有效截止日期")
        AENRA = CharField("更改号到")
        AMGLG = DecimalField("以基本计量单位为准的计算的报废数量", decimals=3)
        AMGKO = DecimalField("以组件计量单位为准的计算的报废数量", decimals=3)
        DUMPS = CharField("虚拟项目标识")

        # 下一级 BOM
        XTLTY = CharField("BOM 类别(下一级别)")
        XTLNR = CharField("物料清单编号 (下一级别)")
        XTLAN = CharField("物料清单用途(下一级别)")
        XTLAL = CharField("BOM可选项(下一级别)")
        XISDT = CharField("标识:日期历史(下一级别)")
        XISSR = CharField("标识:技术状态历史(下一级别)")
        XMENG = DecimalField("物料清单基本数量(下一级别)", decimals=3)
        XMEIN = CharField("基本计量单位物料票据(下一级)")
        XALTS = CharField("标识:可选项(下一级)")
        XVARS = CharField("标识:变式(下一级别)")
        XKBAU = CharField("标识: 可配置的BOM (下一级别)")
        XLOEK = CharField("删除标识(抬头;下一级别)")
        AUSNM = CharField("例外")
        HDNFO = CharField("标志: 表头信息记录")
        AFFLG = CharField("标志: BOM 展开禁止")
        LTFLG = CharField("标志: 禁止显示")
        NLFLG = CharField("标志: 没保存在库存中")

        # 订单展开
        INDEX = IntField("内部表的行索引")
        SUMKZ = CharField("总计记录指示符")
        AUFST = CharField("订单级别")
        AUFWG = CharField("订单路径")
        BAUST = CharField("装配订单级别")
        BAUWG = CharField("装配订单途径")
        ASTOV = IntField("订单级别")
        AWGOV = IntField("订单路径")
        BSTOV = IntField("装配订单层")
        BWGOV = IntField("装配订单途径")
        NLINK = CharField("展开BOM树中的边")
        ALPST = CharField("替代项目：策略")
        ALPRF = CharField("替代项目：评比定单")
        ALPGR = CharField("替代项目：组")
        DSPST = CharField("展开类型")
        KZNFP = CharField("指示符：后继项目")
        NFGRP = CharField("后继组")
        NFEAG = CharField("中止组")
        KZCLB = CharField("指示符：分类作为选择条件")
        CLSZU = CharField("分类号")
        ITMID = CharField("项目外部标识")
        ALEKZ = CharField("ALE指示器")
        GUIDX = Field("项目更改状态全局标识")
        ITSOB = CharField("BOM 项目的特殊采购类型")
        RFPNT = CharField("BOM 传输的参考点")
        SOBMX = CharField("特殊采购类型（物料主数据和项目的合并）")
        MATKL = CharField("物料组")
        INSTS = CharField("实例号在 DDB （配置）内")
        INSTP = CharField("实例号在 DDB （配置）内")
        KSTTY = CharField("原始销售订单 BOM 项目的 BOM 类别")
        KSTNR = CharField("原始销售订单 BOM 项目的物料清单")
        KSTKN = CharField("原始销售订单 BOM 项目的节点号")
        KSTPZ = CharField("原始销售订单 BOM 项目计数器")
        CAALT = CharField("可选的 BOM")
        STLTY_W = CharField("物料清单类别")
        STLNR_W = CharField("物料单")
        SGT_RCAT = CharField("需求段")
        SGT_SCAT = CharField("库存细分")
        BISMT = CharField("旧物料号")

        # 顺威自定义
        ZZFIGURE_NO = CharField("顺威图号")
        ZZMOULD_NO = CharField("顺威可用模号")
        LABST = DecimalField("非限制使用的估价的库存", decimals=3)
        CUFACTOR = CharField("CU：兼容设备实例的数量")
        FUNCID = CharField("功能标识")


class MaterialBomMaintain(RfcSchema):
    """
    新建/修改物料 BOM (ZRFC_BOM_CREATE_FOR_PLM)。

    文档标题写成了「读取物料bom」，与函数名和 I_TYPE 不符。按新建/修改封装。

    SAP 接口:
        - Import: I_TYPE（'N' 新建，'M' 修改）
        - Tables: T_MAIN (ZRFC_BOM_STRU，输入)，T_MSG (BAPIRET2，返回消息)

    注意:
        - T_MAIN 全部是 CHAR，含数量和日期。按字符串传入，不转 Decimal / date。
          读取接口的 DATUV 是 8 位 YYYYMMDD；这里 DATUV 是 CHAR 10，schema 不改写。
        - 不设 msg_type_field。消息在 T_MSG 里，框架不扫 BAPIRET2。
          TYPE='E' 不会抛错，调用方看返回行的 TYPE / MESSAGE。
        - 不填默认的 I_TYPE、工厂或备选。只认 'N' 和 'M'。
        - T_MAIN 不是 OutputTable。内嵌输出表若排在 T_MSG 前面，
          .call() 会返回入参回显而不是消息。

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.bom import MaterialBomMaintain

        msgs = sap.rfc(MaterialBomMaintain).filter(
            i_type="N",
            t_main=[{
                "MATNR": "A02006000027",
                "WERKS": "3011",
                "BMENG": "1000",
                "STLAN": "1",
                "STLAL": "01",
                "STLST": "1",
                "POSNR": "0010",
                "POSTP": "L",
                "IDNRK": "A01005000044",
                "MENGE": "649.800",
                "MEINS": "KG",
                "DATUV": "2026-10-16",
            }],
        ).call()
        for msg in msgs:
            print(msg.TYPE, msg.MESSAGE)
    """

    function_name = "ZRFC_CREATE_MATERIAL_BOM"

    # 列清单。元组不会被元类收成参数或输出表。
    T_MAIN_FIELDS = (
        "MATNR",   # 物料编号
        "WERKS",   # 工厂
        "BMENG",   # 基准数量(BTCI)
        "STLAN",   # BOM 用途
        "POSNR",   # BOM 项目号
        "POSTP",   # 项目类别（物料单）
        "IDNRK",   # 带有转换MATN2的组件(BTCI)
        "MENGE",   # 组件数量 (BTCI)
        "MEINS",   # 组件计量单位
        "POTX1",   # BOM 项目文本（行1）
        "EWAHR",   # 使用可能性按 % (BTCI)
        "STLAL",   # 可选的 BOM
        "STKTX",   # 可选 BOM 文本
        "ZTEXT",   # BOM 文本
        "STLST",   # BOM 状态 (BTCI)
        "AUSCH",   # 部件废品用百分比表示(BTCI)
        "DATUV",   # 有效期自。CHAR 10，不是读取接口的 8 位 YYYYMMDD
    )

    # ---- Import ----
    i_type = ImportParam("I_TYPE")   # "N" 新建，"M" 修改

    # ---- 输入表（行原样传入，不校验、不转换）----
    t_main = TableInput("T_MAIN")

    # ---- 唯一输出表：.call() 返回消息列表 ----
    class T_MSG(OutputTable):
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


class MaterialBomLinkQuery(RfcSchema):
    """
    获取 BOM 表关系链 (ZRFC_GET_MAST)。

    查物料在某工厂挂了哪些 BOM（MAST）：用途、物料单、可选 BOM。
    不展开组件。组件行用 MaterialBomQuery。

    SAP 接口:
        - Import: IS_QUERY (ZSD_QUERY_MAST)
                    ├─ S_MATNR  range, LOW/HIGH 为 MATNR (CHAR40)
                    └─ S_WERKS  range, LOW/HIGH 为 EWERK (CHAR4, 工厂)
        - Export: E_RTYPE, E_RTMSG
        - Tables: IT_ITEM (MAST)

    实测（2026-10-19，工厂 3011）:
        - 有数据：E_RTYPE='S'，E_RTMSG='查询成功'。
          A02006000027 返回 3 行（用途 1/备选 01、用途 2/备选 01、用途 1/备选 02）。
          A02006000028 返回 1 行（用途 1、备选 01、物料单 00042573）。
        - 无数据：E_RTYPE='E'，E_RTMSG='查询不到相关数据'（物料不存在或该工厂没有 BOM）。
          措辞和价格接口的「未查询到相关数据」不同，只认这一句。
        - 返回列比文档多 MANDT，共 13 列。MATNR 无前导零。
          ANDAT 是 YYYYMMDD；AEDAT 为空串时变成 None。

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.bom import MaterialBomLinkQuery

        rows = sap.rfc(MaterialBomLinkQuery).filter(
            s_matnr__eq="A02006000027",
            s_werks__eq="3011",
        ).call()
        for row in rows:
            print(row.WERKS, row.STLAN, row.STLAL, row.STLNR)
    """

    function_name = "ZRFC_GET_MAST"

    msg_type_field = "E_RTYPE"
    msg_text_field = "E_RTMSG"
    # 精确匹配。漏配会把「没有 BOM」抛成 SAPBusinessError；写宽了会吞掉真错误。
    msg_empty_texts = ("查询不到相关数据",)

    # ---- 服务端筛选：两个 range 嵌在 IS_QUERY 内 ----
    s_matnr = RangeTableParam("S_MATNR", field="MATNR", structure="IS_QUERY")
    s_werks = RangeTableParam("S_WERKS", field="WERKS", structure="IS_QUERY")

    # ---- 输出表（列顺序与实测返回一致）----
    class IT_ITEM(OutputTable):
        MANDT = CharField("集团")
        MATNR = CharField("物料编号", converter=clean_leading_zeros)
        WERKS = CharField("工厂")
        STLAN = CharField("BOM 用途")
        STLNR = CharField("物料单")
        STLAL = CharField("可选的 BOM")
        LOSVN = DecimalField("从批量", decimals=3)
        LOSBS = DecimalField("到批量", decimals=3)
        ANDAT = DateField("日期记录创建于")
        ANNAM = CharField("创建记录的用户")
        AEDAT = DateField("最后更改日期")
        AENAM = CharField("更改对象用户的名称")
        CSLTY = CharField("标志: 配置物料(物料变式)")


class MaterialBomDelete(RfcSchema):
    """
    删除物料 BOM (ZRFC_DELETE_MATERIAL_BOM)。

    按物料、工厂、BOM 用途、可选 BOM 删除一张 BOM。没有返回表。

    SAP 接口:
        - Import: I_MATNR, I_WERKS, I_STLAN, I_STALT
        - Export: E_RTYPE, E_RTMSG
        - Tables: 无

    注意:
        - 没有输出表。.call() 成功时只能得到 []，成功文案被丢掉。
          用 sap.call_structured() 才能拿到 E_RTYPE / E_RTMSG。
        - E / A 会抛 SAPBusinessError。删除失败不是空结果，不设 msg_empty_texts。
        - 不填默认工厂、用途或备选。I_STLAN 是 BOM 用途，I_STALT 是可选 BOM，两个都要传。

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.bom import MaterialBomDelete

        result = sap.call_structured(
            MaterialBomDelete,
            i_matnr="A02006000027",
            i_werks="3011",
            i_stlan="1",
            i_stalt="01",
        )
        print(result["E_RTYPE"], result["E_RTMSG"])
    """

    function_name = "ZRFC_DELETE_MATERIAL_BOM"

    msg_type_field = "E_RTYPE"
    msg_text_field = "E_RTMSG"

    # ---- Import 标量参数 ----
    i_matnr = ImportParam("I_MATNR")   # 物料编号
    i_werks = ImportParam("I_WERKS")   # 工厂
    i_stlan = ImportParam("I_STLAN")   # BOM 用途
    i_stalt = ImportParam("I_STALT")   # 可选的 BOM

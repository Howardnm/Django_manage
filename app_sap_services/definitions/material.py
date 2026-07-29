"""
物料主数据 RFC 函数声明式定义。

后期添加新 RFC 时，参考此文件的声明模式:
  1. 继承 RfcSchema
  2. 设置 function_name
  3. 声明 RangeTableParam / ImportParam / TableInput 参数
  4. 声明 OutputTable 内嵌类描述输出字段
"""

from ..schemas import (
    RfcSchema,
    RangeTableParam,
    OutputTable,
    CharField,
)

from ..converters import clean_leading_zeros


class MaterialQuery(RfcSchema):
    """
    物料主数据查询 (ZRFC_MATERIAL_MESN)。

    支持按物料编号、物料类型、工厂、日期范围筛选。

    使用示例:
        from app_sap_services import sap
        from app_sap_services.definitions.material import MaterialQuery

        # 链式调用
        result = sap.rfc(MaterialQuery) \
            .filter(mat_range__cp="A01*") \
            .filter(mta_range__eq="ROH") \
            .filter(wek_range__eq="1010") \
            .limit(50) \
            .call()

        # 快捷调用
        result = sap.call(MaterialQuery, mat_range__cp="A01*", mta_range__eq="ROH")

        for row in result:
            print(row.MATNR, row.MAKTX, row.MTART)
    """

    function_name = "ZRFC_MATERIAL_MESN"

    # ---- 输入参数 (Range Tables) ----
    mat_range = RangeTableParam("MAT_RANGE", field="MATNR")
    wek_range = RangeTableParam("WEK_RANGE", field="WERKS")
    mta_range = RangeTableParam("MTA_RANGE", field="MTART", low_field="MTART_LOW", high_field="MTART_HIGH",)
    dat_range = RangeTableParam("DAT_RANGE", field="ERDAT")

    # ---- 输出表 ----
    class ZMARC(OutputTable):
        MATNR = CharField("物料编号", converter=clean_leading_zeros)
        WERKS = CharField("工厂")
        MAKTX = CharField("物料描述")
        MEINS = CharField("基本计量单位")
        NORMT = CharField("标准/旧料号")
        GROES = CharField("规格")
        MTART = CharField("物料类型")
        MATKL = CharField("物料组")
        LVORM = CharField("删除标识符")
        LVORMC = CharField("删除标识符(工厂)")
        ZZTEXT1 = CharField("物料描述2")
        ZZFIGURE_NO = CharField("图号")

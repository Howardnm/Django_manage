"""定义文件结构回归测试。

验证 RFC 定义（material/price/stock/vendor/bom）的静态结构：
- function_name 正确
- describe() 不报错且含关键信息
- VendorCheckQuery 的输出字段子集符合预期
- MaterialBomQuery 的 GT_STB 列序与类型符合实测接口
"""

from decimal import Decimal

from django.test import SimpleTestCase

from app_sap_services.exceptions import SAPBusinessError
from app_sap_services.schemas import Field, CharField
from app_sap_services.definitions.vendor import VendorCheckQuery
from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.stock import MaterialStockQuery
from app_sap_services.definitions.bom import (
    MaterialBomQuery,
    MaterialBomMaintain,
    MaterialBomLinkQuery,
    MaterialBomDelete,
)


class FunctionNameTest(SimpleTestCase):
    def test_all_function_names(self):
        self.assertEqual(MaterialQuery.function_name, "ZRFC_MATERIAL_MESN")
        self.assertEqual(MaterialPriceQuery.function_name, "ZRFC_GET_MBEWH")
        self.assertEqual(MaterialStockQuery.function_name, "ZRFC_GET_MAT_STOCK")
        self.assertEqual(VendorCheckQuery.function_name, "ZFG_CHECK_VENDOR")
        self.assertEqual(MaterialBomQuery.function_name, "ZRFC_GET_MATERIAL_BOM")
        self.assertEqual(MaterialBomMaintain.function_name, "ZRFC_BOM_CREATE_FOR_PLM")
        self.assertEqual(MaterialBomLinkQuery.function_name, "ZFG_GET_MAST")
        self.assertEqual(MaterialBomDelete.function_name, "ZRFC_DELETE_MATERIAL_BOM")


class MaterialPriceQueryStructureTest(SimpleTestCase):
    """ZRFC_GET_MBEWH 定义结构回归 —— 两个 range 嵌在 IS_QUERY 结构内。"""

    def test_ranges_are_nested_in_is_query(self):
        self.assertEqual(
            MaterialPriceQuery._range_params["s_matnr"].structure, "IS_QUERY"
        )
        self.assertEqual(
            MaterialPriceQuery._range_params["s_bwkey"].structure, "IS_QUERY"
        )

    def test_structure_members(self):
        self.assertEqual(list(MaterialPriceQuery._structures.keys()), ["IS_QUERY"])
        names = {p.rfc_name for p in MaterialPriceQuery._structures["IS_QUERY"]}
        self.assertEqual(names, {"S_MATNR", "S_BWKEY"})

    def test_no_import_scalar_params(self):
        # 新接口没有任何标量 Import —— 期间筛选已下移到客户端
        self.assertEqual(MaterialPriceQuery._import_params, {})

    def test_it_item_has_all_13_fields(self):
        fields = MaterialPriceQuery.IT_ITEM._fields
        for f in ("KALNR", "BDATJ", "POPER", "PEINH", "VPRSV", "STPRS", "PVPRS",
                  "WAERS", "SALK3", "SALKV", "MATNR", "BWKEY", "VERPR"):
            self.assertIn(f, fields, f"IT_ITEM 缺少字段 {f}")
        self.assertEqual(len(fields), 13)

    def test_it_item_field_types(self):
        fields = MaterialPriceQuery.IT_ITEM._fields
        for f in ("BDATJ", "POPER", "PEINH", "KALNR"):
            self.assertEqual(
                type(fields[f]).__name__,
                "IntField" if f != "KALNR" else "CharField",
                f"{f} 类型不符",
            )
        for f in ("STPRS", "PVPRS", "SALK3", "SALKV", "VERPR"):
            self.assertEqual(type(fields[f]).__name__, "DecimalField")
        # MATNR 必须用 clean_leading_zeros 才能对齐 RawMaterial.warehouse_code
        self.assertIsNotNone(fields["MATNR"].converter)

    def test_message_fields_declared(self):
        self.assertEqual(MaterialPriceQuery.msg_type_field, "E_RTYPE")
        self.assertEqual(MaterialPriceQuery.msg_text_field, "E_RTMSG")

    def test_describe_shows_structure_path(self):
        desc = MaterialPriceQuery.describe()
        self.assertIn("IS_QUERY.S_MATNR", desc)
        self.assertIn("IS_QUERY.S_BWKEY", desc)
        self.assertIn("嵌套 Import 结构", desc)

    def test_other_queries_have_no_structures(self):
        for cls in (MaterialQuery, MaterialStockQuery, VendorCheckQuery):
            self.assertEqual(cls._structures, {}, f"{cls.__name__} 不应有嵌套结构")
            self.assertEqual(cls.msg_type_field, "", f"{cls.__name__} 不应开启消息检查")


class DescribeTest(SimpleTestCase):
    def test_describe_contains_function_name(self):
        for cls in (MaterialQuery, MaterialPriceQuery, MaterialStockQuery,
                    VendorCheckQuery, MaterialBomQuery, MaterialBomMaintain,
                    MaterialBomLinkQuery, MaterialBomDelete):
            desc = cls.describe()
            self.assertIn(cls.function_name, desc)

    def test_vendor_describe_lists_imports_and_structures(self):
        desc = VendorCheckQuery.describe()
        for attr in ("I_VENDOR", "I_PUR_ORG", "I_COMP_CODE", "I_SORTL"):
            self.assertIn(attr, desc)
        for t in ("ES_LFA1", "ES_LFM1", "ES_LFB1", "ET_RETURN"):
            self.assertIn(t, desc)


class VendorFieldSubsetTest(SimpleTestCase):
    """VendorCheckQuery 关键字段子集 & 类型/转换器约定。"""

    def test_es_lfa1_fields_and_converter(self):
        fields = VendorCheckQuery.ES_LFA1._fields
        for f in ("MANDT", "LIFNR", "LAND1", "NAME1", "NAME2", "NAME3", "NAME4",
                  "ORT01", "ORT02", "PSTLZ", "REGIO", "SORTL", "STRAS", "MCOD1",
                  "ANRED", "KUNNR", "KTOKK", "BRSCH", "LOEVM", "SPERR", "SPERM",
                  "SPERZ", "SPRAS", "STCD1", "STCD2", "STCEG", "TXJCD", "TELF1",
                  "TELF2", "TELFX", "TELBX", "ERDAT", "ERNAM", "AEDAT"):
            self.assertIn(f, fields, f"ES_LFA1 缺少字段 {f}")
        # 账号类字段应用 clean_leading_zeros
        self.assertIsNotNone(fields["LIFNR"].converter)
        self.assertIsNotNone(fields["KUNNR"].converter)
        # 日期字段类型
        self.assertEqual(type(fields["ERDAT"]).__name__, "DateField")
        self.assertEqual(type(fields["AEDAT"]).__name__, "DateField")

    def test_es_lfm1_fields(self):
        fields = VendorCheckQuery.ES_LFM1._fields
        for f in ("MANDT", "LIFNR", "EKORG", "ERDAT", "ERNAM", "SPERM", "LOEVM",
                  "LFABC", "WAERS", "VERKF", "TELF1", "MINBW", "ZTERM", "INCO1",
                  "INCO2", "WEBRE", "KALSK", "KZAUT", "EKGRP", "XERSY", "PLIFZ",
                  "MRPPP", "LFRHY", "EIKTO", "VSBED", "NRGEW"):
            self.assertIn(f, fields, f"ES_LFM1 缺少字段 {f}")
        self.assertEqual(type(fields["MINBW"]).__name__, "DecimalField")
        self.assertEqual(type(fields["PLIFZ"]).__name__, "IntField")

    def test_es_lfb1_fields(self):
        fields = VendorCheckQuery.ES_LFB1._fields
        for f in ("MANDT", "LIFNR", "BUKRS", "ERDAT", "ERNAM", "SPERR", "LOEVM",
                  "ZUAWA", "AKONT", "BEGRU", "VZSKZ", "ZWELS", "ZTERM", "EIKTO",
                  "ZSABE", "KVERM", "FDGRV", "LNRZE", "LNRZB", "XDEZV", "HBKID"):
            self.assertIn(f, fields, f"ES_LFB1 缺少字段 {f}")

    def test_et_return_fields(self):
        fields = VendorCheckQuery.ET_RETURN._fields
        for f in ("TYPE", "ID", "NUMBER", "MESSAGE", "LOG_NO", "LOG_MSG_NO",
                  "MESSAGE_V1", "MESSAGE_V2", "MESSAGE_V3", "MESSAGE_V4",
                  "PARAMETER", "ROW", "FIELD", "SYSTEM"):
            self.assertIn(f, fields, f"ET_RETURN 缺少字段 {f}")
        self.assertEqual(type(fields["NUMBER"]).__name__, "IntField")
        self.assertEqual(type(fields["ROW"]).__name__, "IntField")

    def test_vendor_import_params(self):
        self.assertEqual(VendorCheckQuery._import_params["i_vendor"].rfc_name, "I_VENDOR")
        self.assertEqual(VendorCheckQuery._import_params["i_pur_org"].rfc_name, "I_PUR_ORG")
        self.assertEqual(VendorCheckQuery._import_params["i_comp_code"].rfc_name, "I_COMP_CODE")
        self.assertEqual(VendorCheckQuery._import_params["i_sortl"].rfc_name, "I_SORTL")


# 2026-10-15 对 ZRFC_GET_MATERIAL_BOM 的实测列序（GT_STB / STPOX，218 列）
_GT_STB_FIELDS = (
    "STUFE,WEGXX,BMTYP,TTIDX,VWEGX,OJTXB,BAUSF,STLAN,STLAL,ALTST,VARST,KBAUS,"
    "LOEKZ,OJTXP,MTART,WERKS,VERID,VPSTA,FSTAT,MMEIN,BWTTY,VPRSV,STPRS,VERPR,"
    "PREIH,SBDKZ,XCHAR,KZECH,KZWSM,MMSTA,MMSTD,MSTAE,MSTDE,ZEINR,ZEIVR,ZEIAR,"
    "ZEIFO,BLATT,BLANZ,DISST,DISMM,SERNP,MNGLG,MNGKO,MSIGN,AUSSS,KAUSF,SOBSL,"
    "SOBSK,KZAUS,AUSDT,NFMAT,RGEKZ,KZDKZ,UMREZ,UMREN,LGPRO,PRCTR,REVLV,KZEFF,"
    "KZKFG,MCUOB,CUOBJ,NCONF,FBSKZ,STAWN,PREFE,MSCHG,FXPRU,MATMK,STABK,DOSTX,"
    "STLTY,STLNR,STLKN,STPOZ,STVKN,DATUV,TECHV,AENNR,ANDAT,ANNAM,AEDAT,AENAM,"
    "IDNRK,PSWRK,POSTP,POSNR,SORTF,MEINS,MENGE,FMENG,AUSCH,AVOAU,NETAU,SCHGT,"
    "BEIKZ,ERSKZ,RVREL,SANFE,SANIN,SANKA,SANKO,SANVS,STKKZ,REKRI,REKRS,CADPO,"
    "NLFZT,NLFZV,NLFMV,VERTI,ALPOS,EWAHR,EKGRP,LIFZT,LIFNR,PREIS,PEINH,WAERS,"
    "SAKTO,ROANZ,ROMS1,ROMS2,ROMS3,ROMEI,ROMEN,RFORM,UPSKZ,LTXSP,POTX1,POTX2,"
    "OBJTY,ITMMK,WEBAZ,DOKAR,DOKNR,DOKVR,DOKTL,CSSTR,CLASS,KLART,INTRM,POTPR,"
    "EKORG,CLOBK,CLMUL,CVIEW,KNOBJ,LGORT,PRVBE,KZKUP,DATUB,AENRA,AMGLG,AMGKO,"
    "DUMPS,XTLTY,XTLNR,XTLAN,XTLAL,XISDT,XISSR,XMENG,XMEIN,XALTS,XVARS,XKBAU,"
    "XLOEK,AUSNM,HDNFO,AFFLG,LTFLG,NLFLG,INDEX,SUMKZ,AUFST,AUFWG,BAUST,BAUWG,"
    "ASTOV,AWGOV,BSTOV,BWGOV,NLINK,ALPST,ALPRF,ALPGR,DSPST,KZNFP,NFGRP,NFEAG,"
    "KZCLB,CLSZU,ITMID,ALEKZ,GUIDX,ITSOB,RFPNT,SOBMX,MATKL,INSTS,INSTP,KSTTY,"
    "KSTNR,KSTKN,KSTPZ,CAALT,STLTY_W,STLNR_W,SGT_RCAT,SGT_SCAT,BISMT,"
    "ZZFIGURE_NO,ZZMOULD_NO,LABST,CUFACTOR,FUNCID"
).split(",")


class MaterialBomQueryStructureTest(SimpleTestCase):
    """ZRFC_GET_MATERIAL_BOM 定义结构回归。不连 SAP。"""

    def test_import_params(self):
        params = MaterialBomQuery._import_params
        self.assertEqual(
            [params[name].rfc_name for name in (
                "i_matnr", "i_werks", "i_stalt", "i_datuv", "i_emeng",
            )],
            ["I_MATNR", "I_WERKS", "I_STALT", "I_DATUV", "I_EMENG"],
        )
        self.assertEqual(MaterialBomQuery._structures, {})
        self.assertEqual(MaterialBomQuery._range_params, {})

    def test_message_fields(self):
        self.assertEqual(MaterialBomQuery.msg_type_field, "E_RTYPE")
        self.assertEqual(MaterialBomQuery.msg_text_field, "E_RTMSG")
        self.assertEqual(MaterialBomQuery.msg_empty_texts, ())

    def test_only_output_table_is_gt_stb(self):
        self.assertEqual(list(MaterialBomQuery._output_tables), ["GT_STB"])

    def test_gt_stb_field_order(self):
        self.assertEqual(list(MaterialBomQuery.GT_STB._fields), _GT_STB_FIELDS)
        self.assertEqual(len(_GT_STB_FIELDS), 218)

    def test_gt_stb_field_types(self):
        fields = MaterialBomQuery.GT_STB._fields
        self.assertIsNotNone(fields["IDNRK"].converter)
        self.assertIsNotNone(fields["NFMAT"].converter)
        self.assertIsNotNone(fields["INTRM"].converter)
        self.assertIsNotNone(fields["LIFNR"].converter)
        self.assertIsNone(fields["BISMT"].converter)
        self.assertEqual(type(fields["MENGE"]).__name__, "DecimalField")
        self.assertEqual(fields["MENGE"].decimals, 3)
        self.assertEqual(type(fields["PREIS"]).__name__, "DecimalField")
        self.assertEqual(fields["PREIS"].decimals, 2)
        self.assertEqual(type(fields["DATUV"]).__name__, "DateField")
        self.assertEqual(type(fields["STUFE"]).__name__, "IntField")
        self.assertIs(type(fields["GUIDX"]), Field)
        self.assertNotIsInstance(fields["GUIDX"], CharField)

    def test_describe_lists_import_and_table(self):
        desc = MaterialBomQuery.describe()
        self.assertIn("ZRFC_GET_MATERIAL_BOM", desc)
        self.assertIn("I_MATNR", desc)
        self.assertIn("GT_STB", desc)

    def test_map_record_conversions(self):
        record = MaterialBomQuery.GT_STB.map_record({
            "IDNRK": "000A01005000044",
            "DATUV": "00000000",
            "MENGE": Decimal("649.800"),
            "GUIDX": b"\x00PV",
        })
        self.assertEqual(record.IDNRK, "A01005000044")
        self.assertIsNone(record.DATUV)
        self.assertEqual(record.MENGE, 649.8)
        self.assertEqual(record.GUIDX, b"\x00PV")


class MaterialBomMaintainStructureTest(SimpleTestCase):
    """ZRFC_BOM_CREATE_FOR_PLM 定义结构回归。不连 SAP。"""

    def test_params(self):
        self.assertEqual(
            MaterialBomMaintain._import_params["i_type"].rfc_name, "I_TYPE"
        )
        self.assertEqual(
            MaterialBomMaintain._table_inputs["t_main"].rfc_name, "T_MAIN"
        )
        self.assertEqual(MaterialBomMaintain._structures, {})
        self.assertEqual(MaterialBomMaintain._range_params, {})
        self.assertEqual(MaterialBomMaintain.msg_type_field, "")
        self.assertEqual(MaterialBomMaintain.msg_text_field, "")

    def test_only_output_table_is_t_msg(self):
        self.assertEqual(list(MaterialBomMaintain._output_tables), ["T_MSG"])

    def test_t_main_fields(self):
        self.assertEqual(
            MaterialBomMaintain.T_MAIN_FIELDS,
            (
                "MATNR", "WERKS", "BMENG", "STLAN", "POSNR", "POSTP", "IDNRK",
                "MENGE", "MEINS", "POTX1", "EWAHR", "STLAL", "STKTX", "ZTEXT",
                "STLST", "AUSCH", "DATUV",
            ),
        )

    def test_build_params_passes_strings_through(self):
        row = {
            "MATNR": "A02006000027",
            "WERKS": "3011",
            "MENGE": "649.800",
            "DATUV": "2026-10-16",
        }
        params = MaterialBomMaintain.build_params(i_type="N", t_main=[row])
        self.assertEqual(params, {"I_TYPE": "N", "T_MAIN": [row]})
        self.assertIsInstance(params["T_MAIN"][0]["MENGE"], str)
        self.assertIsInstance(params["T_MAIN"][0]["DATUV"], str)

    def test_t_msg_matches_vendor_bapiret2(self):
        msg = MaterialBomMaintain.T_MSG._fields
        ret = VendorCheckQuery.ET_RETURN._fields
        self.assertEqual(list(msg), list(ret))
        for name in msg:
            self.assertEqual(type(msg[name]).__name__, type(ret[name]).__name__)

    def test_describe_lists_import_and_tables(self):
        desc = MaterialBomMaintain.describe()
        for token in ("ZRFC_BOM_CREATE_FOR_PLM", "I_TYPE", "T_MAIN", "T_MSG"):
            self.assertIn(token, desc)

    def test_map_record_error_message(self):
        record = MaterialBomMaintain.T_MSG.map_record({
            "TYPE": "E",
            "NUMBER": "001",
            "MESSAGE": "BOM 已存在",
        })
        self.assertEqual(record.TYPE, "E")
        self.assertEqual(record.NUMBER, 1)
        self.assertEqual(record.MESSAGE, "BOM 已存在")


class MaterialBomLinkQueryStructureTest(SimpleTestCase):
    """ZFG_GET_MAST 定义结构回归。不连 SAP。"""

    def test_ranges_are_nested_in_is_query(self):
        self.assertEqual(
            MaterialBomLinkQuery._range_params["s_matnr"].structure, "IS_QUERY"
        )
        self.assertEqual(
            MaterialBomLinkQuery._range_params["s_werks"].structure, "IS_QUERY"
        )
        self.assertEqual(
            MaterialBomLinkQuery._range_params["s_matnr"].rfc_name, "S_MATNR"
        )
        self.assertEqual(
            MaterialBomLinkQuery._range_params["s_werks"].rfc_name, "S_WERKS"
        )
        self.assertEqual(MaterialBomLinkQuery._import_params, {})
        self.assertEqual(list(MaterialBomLinkQuery._structures), ["IS_QUERY"])

    def test_message_fields(self):
        self.assertEqual(MaterialBomLinkQuery.msg_type_field, "E_RTYPE")
        self.assertEqual(MaterialBomLinkQuery.msg_text_field, "E_RTMSG")
        self.assertEqual(MaterialBomLinkQuery.msg_empty_texts, ("查询不到相关数据",))

    def test_only_output_table_is_it_item(self):
        self.assertEqual(list(MaterialBomLinkQuery._output_tables), ["IT_ITEM"])
        self.assertEqual(
            list(MaterialBomLinkQuery.IT_ITEM._fields),
            [
                "MANDT", "MATNR", "WERKS", "STLAN", "STLNR", "STLAL",
                "LOSVN", "LOSBS", "ANDAT", "ANNAM", "AEDAT", "AENAM", "CSLTY",
            ],
        )

    def test_field_types(self):
        fields = MaterialBomLinkQuery.IT_ITEM._fields
        self.assertIsNotNone(fields["MATNR"].converter)
        self.assertEqual(fields["LOSVN"].decimals, 3)
        self.assertEqual(fields["LOSBS"].decimals, 3)
        self.assertEqual(type(fields["ANDAT"]).__name__, "DateField")
        self.assertEqual(type(fields["AEDAT"]).__name__, "DateField")
        self.assertEqual(type(fields["CSLTY"]).__name__, "CharField")

    def test_describe_shows_structure_path(self):
        desc = MaterialBomLinkQuery.describe()
        self.assertIn("ZFG_GET_MAST", desc)
        self.assertIn("IS_QUERY.S_MATNR", desc)
        self.assertIn("IS_QUERY.S_WERKS", desc)
        self.assertIn("IT_ITEM", desc)

    def test_empty_result_text_is_not_an_error(self):
        MaterialBomLinkQuery.check_messages({
            "E_RTYPE": "E",
            "E_RTMSG": "查询不到相关数据",
            "IT_ITEM": [],
        })

    def test_other_error_text_raises(self):
        with self.assertRaises(SAPBusinessError):
            MaterialBomLinkQuery.check_messages({
                "E_RTYPE": "E",
                "E_RTMSG": "无权限",
            })

    def test_build_params_nests_ranges(self):
        params = MaterialBomLinkQuery.build_params(
            s_matnr__eq="A02006000027",
            s_werks__eq="3011",
        )
        self.assertEqual(list(params), ["IS_QUERY"])
        self.assertEqual(
            params["IS_QUERY"]["S_MATNR"],
            [{"SIGN": "I", "OPTION": "EQ", "LOW": "A02006000027", "HIGH": ""}],
        )
        self.assertEqual(
            params["IS_QUERY"]["S_WERKS"],
            [{"SIGN": "I", "OPTION": "EQ", "LOW": "3011", "HIGH": ""}],
        )

    def test_map_record(self):
        record = MaterialBomLinkQuery.IT_ITEM.map_record({
            "MATNR": "000A02006000027",
            "ANDAT": "20251105",
            "AEDAT": "",
            "LOSVN": Decimal("0.000"),
            "STLAL": "01",
        })
        self.assertEqual(record.MATNR, "A02006000027")
        self.assertEqual(record.ANDAT.isoformat(), "2025-11-05")
        self.assertIsNone(record.AEDAT)
        self.assertEqual(record.LOSVN, 0.0)
        self.assertEqual(record.STLAL, "01")


class MaterialBomDeleteStructureTest(SimpleTestCase):
    """ZRFC_DELETE_MATERIAL_BOM 定义结构回归。不连 SAP。"""

    def test_imports_and_no_tables(self):
        params = MaterialBomDelete._import_params
        self.assertEqual(
            [params[name].rfc_name for name in (
                "i_matnr", "i_werks", "i_stlan", "i_stalt",
            )],
            ["I_MATNR", "I_WERKS", "I_STLAN", "I_STALT"],
        )
        self.assertEqual(MaterialBomDelete._output_tables, {})
        self.assertEqual(MaterialBomDelete._table_inputs, {})
        self.assertEqual(MaterialBomDelete._structures, {})
        self.assertEqual(MaterialBomDelete._range_params, {})

    def test_message_fields(self):
        self.assertEqual(MaterialBomDelete.msg_type_field, "E_RTYPE")
        self.assertEqual(MaterialBomDelete.msg_text_field, "E_RTMSG")
        self.assertEqual(MaterialBomDelete.msg_empty_texts, ())

    def test_build_params(self):
        params = MaterialBomDelete.build_params(
            i_matnr="A02006000027",
            i_werks="3011",
            i_stlan="1",
            i_stalt="01",
        )
        self.assertEqual(params, {
            "I_MATNR": "A02006000027",
            "I_WERKS": "3011",
            "I_STLAN": "1",
            "I_STALT": "01",
        })

    def test_describe(self):
        desc = MaterialBomDelete.describe()
        for token in ("ZRFC_DELETE_MATERIAL_BOM", "I_MATNR", "I_WERKS", "I_STLAN", "I_STALT"):
            self.assertIn(token, desc)

    def test_success_message_is_kept(self):
        parsed = MaterialBomDelete.parse_response({
            "E_RTYPE": "S",
            "E_RTMSG": "删除成功",
        })
        self.assertEqual(parsed["E_RTYPE"], "S")
        self.assertEqual(parsed["E_RTMSG"], "删除成功")

    def test_error_raises(self):
        with self.assertRaises(SAPBusinessError):
            MaterialBomDelete.parse_response({
                "E_RTYPE": "E",
                "E_RTMSG": "BOM 不存在",
            })
"""
物料主数据 SAP 服务。

已实现 RFC:
- ZRFC_MATERIAL_MESN  — 物料主数据查询 (MES 系统)
- ZFG_CHECK_MATERIAL  — 物料校验 (OA 系统)

添加新 RFC 方法时遵循三步模式:
  1. 用 self.build_range() 或 SAPFilter 构建筛选条件
  2. 用 self._call_rfc() 调用 RFC
  3. 用 self.parse_result() 解析返回结果
"""

from typing import Dict, List, Optional

from ..base import BaseSAPService
from ..filters import SAPFilter


class MaterialService(BaseSAPService):
    """
    物料主数据查询服务。

    使用示例:
        from app_sap_services import sap_material

        # 模糊查询 A01 开头的原材料
        materials = sap_material.query_materials(mat_nr='A01*', mat_type='ROH')

        # 精确查询
        materials = sap_material.query_materials(mat_nr='A01001000003')

        # 校验物料是否存在
        result = sap_material.check_material('A01001000003')
    """

    FIELD_NAME_MAP = {
        'MATNR': ('LOW', 'HIGH'),         # 物料编号 — 标准字段名
        'WERKS': ('LOW', 'HIGH'),         # 工厂 — 标准字段名
        'MTART': ('MTART_LOW', 'MTART_HIGH'),  # 物料类型 — 特殊字段名
        'MATKL': ('MATKL_LOW', 'MATKL_HIGH'),  # 物料组 — 特殊字段名
    }

    # ==================================================================
    # ZRFC_MATERIAL_MESN — 物料主数据查询
    # ==================================================================

    def query_materials(
        self,
        mat_nr: Optional[str] = None,
        mat_type: Optional[str] = None,
        plant: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[Dict]:
        """
        查询物料主数据 (RFC: ZRFC_MATERIAL_MESN)。

        Args:
            mat_nr: 物料编号筛选条件
                    - 精确查询: 'A01001000003'
                    - 模糊查询: 'A01001*' (所有 A01001 开头的物料)
                    - 可使用 * 作通配符，如 '*ROH*' 匹配含 ROH 的编号
            mat_type: 物料类型筛选
                      - 'ROH'  = 原材料 (Raw Material)
                      - 'HALB' = 半成品 (Semi-finished)
                      - 'FERT' = 成品 (Finished Product)
                      - 'HAWA' = 贸易商品
                      - 'Z005' = 试验料
            plant: 工厂代码筛选
                   - '1010' = 广东顺采
                   - '2010' = 佛山顺采
                   - '2020' = 武汉顺采
            date_from: 日期范围-起始 (格式: YYYYMMDD)，如 '20240101'
            date_to:   日期范围-截止 (格式: YYYYMMDD)
            max_results: 最大返回条数，None 表示不限制

        Returns:
            list[dict]: 物料列表，每条记录包含:
                MATNR      — 物料编号 (SAP 原始值, 可能带前导零)
                MATNR_CLEAN— 物料编号 (去除前导零)
                MAKTX      — 物料描述
                MTART      — 物料类型
                MATKL      — 物料组
                MEINS      — 基本单位
                NORMT      — 标准/旧料号
                ZZFIGURE_NO— 图号
                WERKS      — 工厂
                GROES      — 规格
                ZZTEXT1    — 备注
        """
        # --- 第1步: 构建筛选条件 ---
        table_params = {}

        if mat_nr is not None:
            # 自动判断: 含 * 或 ? 则用 CP(包含模式), 否则用 EQ(精确)
            if '*' in mat_nr or '?' in mat_nr:
                option = 'CP'  # Contains Pattern — 支持通配符
            else:
                option = 'EQ'  # Equal — 精确匹配
            table_params['MAT_RANGE'] = [self.build_range(
                sign='I',
                option=option,
                low=mat_nr,
            )]

        if mat_type is not None:
            # 注意: MTA_RANGE 的字段名是 MTART_LOW / MTART_HIGH 而非 LOW / HIGH
            table_params['MTA_RANGE'] = [self.build_range(
                sign='I',
                option='EQ',
                MTART_LOW=mat_type,
                MTART_HIGH='',
            )]

        if plant is not None:
            table_params['WEK_RANGE'] = [self.build_range(
                sign='I',
                option='EQ',
                low=plant,
            )]

        if date_from or date_to:
            option = 'BT' if (date_from and date_to) else ('GE' if date_from else 'LE')
            table_params['DAT_RANGE'] = [self.build_range(
                sign='I',
                option=option,
                low=date_from or '',
                high=date_to or '',
            )]

        # --- 第2步: 调用 RFC ---
        result = self._call_rfc('ZRFC_MATERIAL_MESN', **table_params)

        # --- 第3步: 解析结果 ---
        materials = self.parse_result(result, 'ZMARC')

        # 后处理: 清理物料编号前导零
        for m in materials:
            m['MATNR_CLEAN'] = self.clean_material_no(m.get('MATNR', ''))

        if max_results is not None:
            materials = materials[:max_results]

        return materials

    # ==================================================================
    # ZFG_CHECK_MATERIAL — 物料校验
    # ==================================================================

    def check_material(self, material_code: str) -> Dict:
        """
        校验物料编码是否在 SAP 中存在 (RFC: ZFG_CHECK_MATERIAL)。

        Args:
            material_code: 物料编码，如 'A01001000003'

        Returns:
            dict: SAP 原始返回结果（具体字段待实际调用后确认）
        """
        result = self._call_rfc('ZFG_CHECK_MATERIAL', MATNR=material_code)
        return result

    # ==================================================================
    # 高级查询 (使用 SAPFilter 链式构建)
    # ==================================================================

    def query_materials_advanced(
        self,
        mat_filters: Optional[List[Dict]] = None,
        mta_filters: Optional[List[Dict]] = None,
        wek_filters: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        高级物料查询 — 支持多条件组合。

        调用方自行用 SAPFilter 构建筛选条件，传入此方法执行。

        Args:
            mat_filters: MAT_RANGE 过滤条件列表
            mta_filters: MTA_RANGE 过滤条件列表 (物料类型)
            wek_filters: WEK_RANGE 过滤条件列表 (工厂)

        Returns:
            list[dict]: 物料列表

        Example:
            from app_sap_services.filters import SAPFilter

            mat_range = (
                SAPFilter(field='MATNR')
                .include_pattern('A01*', help_text='A01 开头的原材料')
                .include_pattern('B02*', help_text='B02 开头的辅料')
                .build()
            )

            mta_range = (
                SAPFilter(field='MTART')
                .include_eq('ROH', help_text='原材料')
                .include_eq('HAWA', help_text='贸易商品')
                .build()
            )

            materials = sap_material.query_materials_advanced(
                mat_filters=mat_range,
                mta_filters=mta_range,
            )
        """
        table_params = {}
        if mat_filters:
            table_params['MAT_RANGE'] = mat_filters
        if mta_filters:
            table_params['MTA_RANGE'] = mta_filters
        if wek_filters:
            table_params['WEK_RANGE'] = wek_filters

        result = self._call_rfc('ZRFC_MATERIAL_MESN', **table_params)
        materials = self.parse_result(result, 'ZMARC')

        for m in materials:
            m['MATNR_CLEAN'] = self.clean_material_no(m.get('MATNR', ''))

        return materials

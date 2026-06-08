"""
SAP Range Table 过滤条件构建器。

提供链式 API 构建 SAP 筛选条件，每个条件可附加中文 help_text 注释。
IT 人员可通过 describe() 方法查看人类可读的过滤说明。

SAP Range Table 字段说明:
  SIGN:   'I' = 包含(Include), 'E' = 排除(Exclude)
  OPTION: 'EQ' = 等于, 'NE' = 不等于, 'BT' = 介于(Between), 'NB' = 不介于
          'CP' = 包含模式(支持通配符 *), 'NP' = 不包含模式
          'GT' = 大于, 'LT' = 小于, 'GE' = 大于等于, 'LE' = 小于等于
  LOW:    下限值/单个值，CP 模式下 * 代表任意字符 (e.g., 'A01*')
  HIGH:   上限值（仅 BT/NB 模式使用）

用法示例:
    # 方式1: 链式构建
    mat_range = (
        SAPFilter(field='MATNR')
        .include_pattern('A01*', help_text='A01开头的原材料')
        .include_eq('B0200500001', help_text='指定辅料')
        .exclude_eq('000000000000000001', help_text='排除占位物料')
        .build()
    )

    # 方式2: 快捷类方法
    mat_range = SAPFilter.material_pattern('A01001*')

    # 方式3: 查看过滤条件说明
    f = SAPFilter(field='MTART').include_eq('ROH', help_text='原材料类型')
    print(f.describe())  # → 人类可读的过滤说明
"""

from typing import Dict, List, Optional, Any
from .exceptions import SAPFilterError


class SAPFilter:
    """SAP Range Table 构建器"""

    # OPTION 中文说明映射
    OPTION_HELP = {
        'EQ': '等于（精确匹配）',
        'NE': '不等于',
        'BT': '介于（LOW ≤ x ≤ HIGH）—— 需同时填 LOW 和 HIGH',
        'NB': '不介于',
        'CP': '包含模式（支持通配符 *）—— 如 "A01*" 匹配所有A01开头的值',
        'NP': '不包含模式',
        'GT': '大于',
        'LT': '小于',
        'GE': '大于等于',
        'LE': '小于等于',
    }

    # 物料类型枚举参考
    MATERIAL_TYPES = {
        'ROH': '原材料 (Raw Material)',
        'HALB': '半成品 (Semi-Finished)',
        'FERT': '成品 (Finished Product)',
        'HAWA': '贸易商品 (Trading Goods)',
        'Z005': '试验料',
    }

    def __init__(self, field: str = ''):
        """
        初始化过滤器

        Args:
            field: SAP 字段名，如 'MATNR', 'MTART', 'WERKS'
        """
        self._field = field
        self._entries: List[Dict[str, str]] = []
        self._help_notes: List[str] = []

    # -- 静态工厂方法 -------------------------------------------------

    @classmethod
    def field(cls, field_name: str) -> 'SAPFilter':
        """为指定字段创建过滤器"""
        return cls(field=field_name)

    @classmethod
    def material_pattern(cls, pattern: str) -> List[Dict]:
        """快捷方法：物料编号模糊匹配（CP 模式，单个条件）"""
        return cls(field='MATNR').include_pattern(pattern).build()

    @classmethod
    def material_eq(cls, matnr: str) -> List[Dict]:
        """快捷方法：物料编号精确匹配（EQ 模式，单个条件）"""
        return cls(field='MATNR').include_eq(matnr).build()

    @classmethod
    def material_type_eq(cls, mtart: str) -> List[Dict]:
        """快捷方法：物料类型精确匹配，使用 MTART_LOW/HIGH 字段名"""
        return [{
            'SIGN': 'I',
            'OPTION': 'EQ',
            'MTART_LOW': mtart,
            'MTART_HIGH': '',
        }]

    # -- 包含条件 (SIGN='I') ------------------------------------------

    def include_eq(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """【EQ】精确等于 low 的值"""
        self._add_entry('I', 'EQ', str(low) if low else '', '', help_text)
        return self

    def include_pattern(self, pattern: str, help_text: str = '') -> 'SAPFilter':
        """【CP】包含模式匹配，通配符 * 代表任意字符。如 'A01*' 匹配所有 A01 开头的值"""
        self._add_entry('I', 'CP', pattern, '', help_text)
        return self

    def include_between(self, low: Any, high: Any, help_text: str = '') -> 'SAPFilter':
        """【BT】介于 low 和 high 之间（含边界）"""
        self._add_entry('I', 'BT', str(low), str(high), help_text)
        return self

    def include_gt(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """【GT】大于 low"""
        self._add_entry('I', 'GT', str(low), '', help_text)
        return self

    def include_ge(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """【GE】大于等于 low"""
        self._add_entry('I', 'GE', str(low), '', help_text)
        return self

    def include_le(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """【LE】小于等于 low"""
        self._add_entry('I', 'LE', str(low), '', help_text)
        return self

    def include_lt(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """【LT】小于 low"""
        self._add_entry('I', 'LT', str(low), '', help_text)
        return self

    # -- 排除条件 (SIGN='E') ------------------------------------------

    def exclude_eq(self, low: Any, help_text: str = '') -> 'SAPFilter':
        """排除精确等于 low 的值"""
        self._add_entry('E', 'EQ', str(low) if low else '', '', help_text)
        return self

    def exclude_pattern(self, pattern: str, help_text: str = '') -> 'SAPFilter':
        """排除模式匹配的值"""
        self._add_entry('E', 'CP', pattern, '', help_text)
        return self

    # -- 内部方法 -----------------------------------------------------

    def _add_entry(self, sign: str, option: str, low: str, high: str, note: str):
        self._entries.append({
            'SIGN': sign,
            'OPTION': option,
            'LOW': low,
            'HIGH': high,
        })
        if note:
            opt_cn = self.OPTION_HELP.get(option, option)
            self._help_notes.append(f"[{sign}/{option}({opt_cn})] {note}")

    # -- 输出方法 -----------------------------------------------------

    def build(self) -> List[Dict]:
        """构建并返回 range table 列表，可直接传入 RFC 调用"""
        return self._entries

    def describe(self) -> str:
        """返回人类可读的过滤条件说明（用于调试/日志）"""
        if not self._help_notes:
            return f"SAPFilter(field={self._field}, entries={len(self._entries)})"
        header = f"SAPFilter(field={self._field}):"
        items = "\n  ".join(self._help_notes)
        return f"{header}\n  {items}"

    def __repr__(self) -> str:
        return self.describe()

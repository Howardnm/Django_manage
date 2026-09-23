"""MCP 序列化层的空值约定：空属性一律 null，不出现 "N/A" / "None" 这类字符串哨兵。"""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from app_mcp_server.serializers.base import (
    FloatDecimalField,
    NADateField,
    NADateTimeMinuteField,
    blank_to_none,
    format_date,
    json_number,
)
from app_mcp_server.serializers.material import MaterialSerializer


class NullConventionTests(SimpleTestCase):
    def test_blank_to_none(self):
        self.assertIsNone(blank_to_none(""))
        self.assertIsNone(blank_to_none(None))
        self.assertEqual(blank_to_none("x"), "x")
        # 0 是真实值，不能被当成空
        self.assertEqual(blank_to_none(0), 0)
        self.assertEqual(blank_to_none(False), False)

    def test_format_date(self):
        self.assertEqual(format_date(datetime(2026, 9, 22)), "2026-09-22")
        self.assertIsNone(format_date(None))

    def test_date_fields_return_null_not_sentinel(self):
        self.assertIsNone(NADateField().to_representation(None))
        self.assertEqual(
            NADateField().to_representation(datetime(2026, 9, 22)), "2026-09-22",
        )
        self.assertIsNone(NADateTimeMinuteField().to_representation(None))
        self.assertEqual(
            NADateTimeMinuteField().to_representation(datetime(2026, 9, 22, 13, 5)),
            "2026-09-22 13:05",
        )

    def test_float_decimal_keeps_null_and_zero_apart(self):
        field = FloatDecimalField()
        self.assertIsNone(field.to_representation(None))
        self.assertEqual(field.to_representation(Decimal("0")), 0.0)
        self.assertEqual(field.to_representation(Decimal("12.5")), 12.5)

    def test_json_number(self):
        self.assertIsNone(json_number(None))
        self.assertEqual(json_number(Decimal("1.5")), 1.5)
        self.assertEqual(json_number("HB"), "HB")


class PropertiesSummaryTests(SimpleTestCase):
    """get_properties_summary 以前会把 None 写成字符串 "None"，agent 当真实测量值读。"""

    def _material_stub(self, items):
        obj = SimpleNamespace(
            get_grouped_properties=lambda: [{"category_name": "力学", "items": items}],
        )
        return obj

    def _summary(self, items):
        serializer = MaterialSerializer()
        return serializer.get_properties_summary(self._material_stub(items))

    def test_value_with_unit(self):
        summary = self._summary([{
            "name": "拉伸强度", "standard": "ISO 527",
            "value": 75.5, "unit": "MPa",
        }])
        self.assertEqual(summary["拉伸强度 (ISO 527)"], "75.5 MPa")

    def test_missing_value_is_null_not_the_string_none(self):
        summary = self._summary([{
            "name": "阻燃测试", "standard": "UL94",
            "value": None, "unit": None,
        }])
        self.assertIsNone(summary["阻燃测试 (UL94)"])

    def test_text_value_without_unit(self):
        summary = self._summary([{
            "name": "阻燃等级", "standard": "UL94",
            "value": "V-0", "unit": "",
        }])
        self.assertEqual(summary["阻燃等级 (UL94)"], "V-0")

    def test_zero_is_a_real_value(self):
        summary = self._summary([{
            "name": "收缩率", "standard": "ISO 294",
            "value": 0, "unit": "%",
        }])
        self.assertEqual(summary["收缩率 (ISO 294)"], "0 %")

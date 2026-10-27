"""配方份数 → SAP 行。不连接 SAP。"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry, FormulaBOM, LabFormula
from app_material.models import MaterialLibrary, MaterialType
from app_material.services.finished_bom_publish import (
    FinishedBomPublishError,
    build_sap_lines,
    publish_finished_bom,
)
from app_project.models import Project
from app_raw_material.models import RawMaterial, RawMaterialType

User = get_user_model()


class PublishMappingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bom-pub", password="x")
        cls.material_type = MaterialType.objects.create(name="发布映射-工程塑料")
        cls.resin = RawMaterialType.objects.create(name="发布映射-树脂", order=1)
        cls.filler = RawMaterialType.objects.create(name="发布映射-填充", order=2)
        cls.finished = MaterialLibrary.objects.create(
            grade_name="发布映射成品", sap_material_code="A-PUB-01",
            category=cls.material_type, creator=cls.user,
        )
        cls.project = Project.objects.create(
            code="P-PUB", name="发布映射项目", manager=cls.user, material=cls.finished,
        )

    def _formula(self, code="L-PUB"):
        return LabFormula.objects.create(
            name="映射配方", code=code, material_type=self.material_type,
            project=self.project, creator=self.user,
        )

    def _raw(self, name, code, category):
        return RawMaterial.objects.create(
            name=name, warehouse_code=code, category=category,
        )

    def _line(self, formula, raw, percentage, feeding="1_MAIN"):
        return FormulaBOM.objects.create(
            formula=formula, raw_material=raw, percentage=Decimal(percentage),
            feeding_port=feeding,
        )

    def test_scales_parts_into_grams_and_keeps_base_in_kilograms(self):
        formula = self._formula()
        # 侧喂先入库，行号更小。排序仍应让主喂在前。
        self._line(formula, self._raw("填充", "A-FILL", self.filler), "40", "2_SIDE_1")
        self._line(formula, self._raw("树脂", "A-RESIN", self.resin), "60")

        lines = build_sap_lines(
            formula, bmeng=Decimal("1000"), datuv="2026-10-26",
            stlst="01", stktx="可选文本", ztext="抬头", merge_color=False,
        )

        self.assertEqual([row["idnrk"] for row in lines], ["A-RESIN", "A-FILL"])
        self.assertEqual(lines[0]["posnr"], "0010")
        self.assertEqual(lines[0]["postp"], "L")
        self.assertEqual(lines[0]["menge"], "600000.000")
        self.assertEqual(lines[0]["meins"], "G")
        self.assertEqual(lines[0]["bmeng"], "1000")
        self.assertEqual(lines[0]["ausch"], "1")
        self.assertEqual(lines[0]["datuv"], "2026-10-26")
        self.assertEqual(lines[0]["stlst"], "01")
        self.assertEqual(lines[1]["menge"], "400000.000")
        self.assertEqual(lines[1]["posnr"], "0020")

    def test_color_is_appended_and_not_renormalized(self):
        formula = self._formula("L-COLOR")
        self._line(formula, self._raw("树脂", "A-RESIN-C", self.resin), "60")
        self._line(formula, self._raw("填充", "A-FILL-C", self.filler), "40")
        color = ColorPowderBOM.objects.create(formula=formula, filled_by=self.user)
        ColorPowderBOMEntry.objects.create(
            color_powder_bom=color,
            raw_material=self._raw("色粉", "A-COLOR", self.filler),
            percentage=Decimal("2"),
        )

        lines = build_sap_lines(
            formula, bmeng=Decimal("1000"), datuv="2026-10-26",
            stlst="", stktx="", ztext="", merge_color=True,
        )

        self.assertEqual([row["idnrk"] for row in lines], ["A-RESIN-C", "A-FILL-C", "A-COLOR"])
        self.assertEqual(lines[2]["menge"], "20000.000")
        self.assertEqual(lines[2]["bmeng"], "1000")

    def test_without_merge_a_color_row_missing_a_code_is_ignored(self):
        formula = self._formula("L-SKIP")
        self._line(formula, self._raw("树脂", "A-RESIN-S", self.resin), "100")
        color = ColorPowderBOM.objects.create(formula=formula)
        ColorPowderBOMEntry.objects.create(
            color_powder_bom=color,
            raw_material=RawMaterial.objects.create(
                name="无编码色粉", category=self.filler, warehouse_code=None,
            ),
            percentage=Decimal("2"),
        )

        lines = build_sap_lines(
            formula, bmeng=Decimal("1000"), datuv="2026-10-26",
            stlst="", stktx="", ztext="", merge_color=False,
        )
        self.assertEqual(len(lines), 1)

        with self.assertRaises(FinishedBomPublishError) as raised:
            build_sap_lines(
                formula, bmeng=Decimal("1000"), datuv="2026-10-26",
                stlst="", stktx="", ztext="", merge_color=True,
            )
        self.assertIn("无编码色粉", str(raised.exception))

    def test_missing_main_code_rejects_the_whole_publish(self):
        formula = self._formula("L-MISS")
        self._line(formula, self._raw("树脂", "A-RESIN-M", self.resin), "60")
        self._line(
            formula,
            RawMaterial.objects.create(name="无编码主料", category=self.filler, warehouse_code=None),
            "40",
        )

        with self.assertRaises(FinishedBomPublishError) as raised:
            build_sap_lines(
                formula, bmeng=Decimal("1000"), datuv="2026-10-26",
                stlst="", stktx="", ztext="", merge_color=False,
            )
        self.assertIn("无编码主料", str(raised.exception))

    def test_same_component_is_summed_before_scaling(self):
        formula = self._formula("L-SUM")
        raw = self._raw("树脂", "A-RESIN-SUM", self.resin)
        self._line(formula, raw, "30")
        self._line(formula, raw, "30", "2_SIDE_1")

        lines = build_sap_lines(
            formula, bmeng=Decimal("1000"), datuv="2026-10-26",
            stlst="", stktx="", ztext="", merge_color=False,
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["menge"], "600000.000")
        self.assertEqual(lines[0]["posnr"], "0010")

    def test_create_and_update_send_the_same_lines(self):
        formula = self._formula("L-MODE")
        self._line(formula, self._raw("树脂", "A-RESIN-MODE", self.resin), "60")
        self._line(formula, self._raw("填充", "A-FILL-MODE", self.filler), "40")
        payload = dict(
            formula_id=formula.pk, werks="3011", stlan="1", stlal="01",
            bmeng=Decimal("1000"), datuv=date(2026, 10, 26),
            merge_color=False,
        )

        with patch("app_material.services.finished_bom_publish.create_bom") as create, \
             patch("app_material.services.finished_bom_publish.update_bom") as update:
            create.return_value = [{"type": "S", "text": "成功"}]
            update.return_value = [{"type": "S", "text": "成功"}]
            created = publish_finished_bom(**payload, mode="create")
            updated = publish_finished_bom(**payload, mode="update")

        create.assert_called_once()
        update.assert_called_once()
        self.assertEqual(create.call_args.kwargs["lines"], update.call_args.kwargs["lines"])
        self.assertEqual(create.call_args.kwargs["matnr"], "A-PUB-01")
        self.assertEqual(created["mode"], "create")
        self.assertEqual(updated["mode"], "update")
        self.assertEqual(create.call_args.kwargs["lines"][0]["menge"], "600000.000")
        self.assertEqual(create.call_args.kwargs["lines"][0]["ausch"], "1")
        self.assertEqual(create.call_args.kwargs["lines"][0]["stlst"], "1")

    def test_formula_without_a_finished_material_is_rejected(self):
        formula = LabFormula.objects.create(
            name="无项目", code="L-NONE", material_type=self.material_type, creator=self.user,
        )
        with self.assertRaises(FinishedBomPublishError):
            publish_finished_bom(
                formula_id=formula.pk, werks="3011", stlan="1", stlal="01",
                bmeng=Decimal("1000"), datuv=date(2026, 10, 26), mode="create",
            )

    def test_empty_bom_is_rejected(self):
        formula = self._formula("L-EMPTY")
        with self.assertRaisesMessage(FinishedBomPublishError, "至少一行"):
            build_sap_lines(
                formula, bmeng=Decimal("1000"), datuv="2026-10-26",
                stlst="", stktx="", ztext="", merge_color=False,
            )

"""原材料同步的工厂写入。不连接 SAP。"""

import polars as pl
from django.test import TestCase

from app_raw_material.models import Plant, RawMaterial, RawMaterialType
from app_sap_services.management.commands.sync_raw_materials import Command


def _frame(rows):
    return pl.DataFrame({
        "MATNR": [row[0] for row in rows],
        "MAKTX": [row[1] for row in rows],
        "WERKS": [row[2] for row in rows],
    })


class SyncRawMaterialPlantTests(TestCase):
    def setUp(self):
        self.default = RawMaterialType.objects.create(name="未分类", code="UNKNOWN")
        self.cleaned = RawMaterialType.objects.create(name="树脂", code="RESIN")
        self.command = Command()

    def test_one_code_keeps_every_plant_and_creates_missing_plants(self):
        Plant.objects.create(code="3011", name="广东")
        self.command._live_sync(_frame([
            ("A010020256", "原料ABS", "3011"),
            ("A010020256", "原料ABS", "1011"),
        ]), self.default)

        material = RawMaterial.objects.get(warehouse_code="A010020256")
        self.assertEqual(
            set(material.plants.values_list("code", flat=True)),
            {"3011", "1011"},
        )
        self.assertEqual(Plant.objects.get(code="3011").name, "广东")
        self.assertEqual(Plant.objects.get(code="1011").name, "")

    def test_plant_set_is_replaced_by_this_run(self):
        material = RawMaterial.objects.create(
            name="原料ABS", warehouse_code="A010020256", category=self.default,
        )
        gone = Plant.objects.create(code="2071")
        material.plants.add(gone)

        self.command._live_sync(_frame([
            ("A010020256", "原料ABS", "3011"),
        ]), self.default)

        self.assertEqual(
            list(material.plants.values_list("code", flat=True)),
            ["3011"],
        )

    def test_cleaned_name_stays_but_plants_are_still_written(self):
        RawMaterial.objects.create(
            name="文员改过的名字", warehouse_code="A010020256", category=self.cleaned,
        )

        self.command._live_sync(_frame([
            ("A010020256", "SAP描述", "3011"),
            ("A010020256", "SAP描述", "3031"),
        ]), self.default)

        material = RawMaterial.objects.get(warehouse_code="A010020256")
        self.assertEqual(material.name, "文员改过的名字")
        self.assertEqual(material.category_id, self.cleaned.pk)
        self.assertEqual(
            set(material.plants.values_list("code", flat=True)),
            {"3011", "3031"},
        )

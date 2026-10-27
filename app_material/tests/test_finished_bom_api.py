"""成品 BOM 本地接口：树、工厂、发布入参。不连接 SAP。"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry, FormulaBOM, LabFormula
from app_material.models import MaterialLibrary, MaterialType
from app_project.models import Project, ProjectNode
from app_raw_material.models import Plant, RawMaterial, RawMaterialType

User = get_user_model()


class FinishedBomApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bom-api", password="x")
        cls.material_type = MaterialType.objects.create(name="接口-工程塑料")
        cls.raw_type = RawMaterialType.objects.create(name="接口-树脂", order=1)
        cls.material = MaterialLibrary.objects.create(
            grade_name="接口成品", sap_material_code="A-API-01",
            category=cls.material_type, creator=cls.user,
        )
        cls.project = Project.objects.create(
            code="P-API", name="接口项目", manager=cls.user, material=cls.material,
        )
        cls.node = ProjectNode.objects.create(
            project=cls.project, stage="PILOT", round=2, order=1,
        )
        cls.raw = RawMaterial.objects.create(
            name="PA66", warehouse_code="A-API-RAW", category=cls.raw_type,
        )
        cls.version = LabFormula.objects.create(
            name="第一版", code="L-API", material_type=cls.material_type,
            project=cls.project, project_node=cls.node, version=1, creator=cls.user,
        )
        FormulaBOM.objects.create(
            formula=cls.version, raw_material=cls.raw, percentage=Decimal("100"),
        )
        cls.later = LabFormula.objects.create(
            name="第二版", code="L-API", material_type=cls.material_type,
            project=cls.project, project_node=cls.node, version=2,
            is_mature=True, creator=cls.user,
        )
        color = ColorPowderBOM.objects.create(formula=cls.later)
        ColorPowderBOMEntry.objects.create(
            color_powder_bom=color, raw_material=cls.raw, percentage=Decimal("0.004936"),
        )
        cls.loose = LabFormula.objects.create(
            name="未挂阶段", code="L-LOOSE", material_type=cls.material_type,
            project=cls.project, creator=cls.user,
        )
        Plant.objects.create(code="3011", name="上海工厂", is_active=True)
        Plant.objects.create(code="3099", name="停用工厂", is_active=False)

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_is_forbidden(self):
        self.client.logout()
        for url in (
            reverse("finished-bom-list"),
            reverse("finished-bom-plants"),
            reverse("finished-bom-packaging"),
            reverse("finished-bom-publish"),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.json()["code"], "not_authenticated")

    def test_unknown_code_is_404(self):
        response = self.client.get(reverse("finished-bom-list"), {"sap_code": "NO-SUCH"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_tree_groups_stage_then_experiment_then_version(self):
        response = self.client.get(reverse("finished-bom-list"), {"sap_code": "A-API-01"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["material"]["grade_name"], "接口成品")
        project = body["projects"][0]
        self.assertEqual(project["code"], "P-API")
        stage, loose = project["nodes"]
        self.assertIn("客户小试", stage["label"])
        self.assertIn("第2轮", stage["label"])
        self.assertFalse(stage["unassigned"])
        experiment = stage["formulas"][0]
        self.assertEqual(experiment["code"], "L-API")
        self.assertEqual(experiment["name"], "第二版")
        first, second = experiment["versions"]
        self.assertEqual(first["version"], 1)
        self.assertFalse(first["has_color_bom"])
        self.assertEqual(first["main_lines"][0]["warehouse_code"], "A-API-RAW")
        self.assertEqual(first["main_lines"][0]["category_name"], "接口-树脂")
        self.assertEqual(first["main_lines"][0]["percentage"], "100.000")
        self.assertFalse(first["main_lines"][0]["missing_sap_code"])
        self.assertTrue(second["is_mature"])
        self.assertTrue(second["has_color_bom"])
        self.assertEqual(second["color_lines"][0]["percentage"], "0.004936")
        self.assertTrue(loose["unassigned"])
        self.assertEqual(loose["formulas"][0]["code"], "L-LOOSE")

    def test_plants_skip_inactive(self):
        response = self.client.get(reverse("finished-bom-plants"))
        codes = [row["code"] for row in response.json()["results"]]
        self.assertIn("3011", codes)
        self.assertNotIn("3099", codes)

    def test_base_quantity_must_be_positive(self):
        response = self.client.post(
            reverse("finished-bom-publish"),
            data={
                "formula_id": self.version.pk,
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "bmeng": "0",
                "datuv": "2026-10-26",
                "mode": "create",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_base_quantity_must_be_an_integer(self):
        response = self.client.post(
            reverse("finished-bom-publish"),
            data={
                "formula_id": self.version.pk,
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "bmeng": "1000.5",
                "datuv": "2026-10-26",
                "mode": "create",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_scrap_cannot_be_negative(self):
        response = self.client.post(
            reverse("finished-bom-publish"),
            data={
                "formula_id": self.version.pk,
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "bmeng": "1000",
                "datuv": "2026-10-26",
                "ausch": "-1",
                "mode": "create",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_missing_formula_is_404(self):
        response = self.client.post(
            reverse("finished-bom-publish"),
            data={
                "formula_id": 999999,
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "bmeng": "1000",
                "datuv": "2026-10-26",
                "mode": "update",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_packaging_search_filters_code_name_and_plant(self):
        shanghai = Plant.objects.get(code="3011")
        stopped = Plant.objects.get(code="3099")
        bag = RawMaterial.objects.create(
            name="PE袋", warehouse_code="K090150001", category=self.raw_type,
        )
        bag.plants.add(shanghai, stopped)
        other = RawMaterial.objects.create(
            name="纸箱", warehouse_code="K090150002", category=self.raw_type,
        )
        other.plants.add(stopped)
        RawMaterial.objects.create(
            name="不是袋子", warehouse_code="A090150001", category=self.raw_type,
        )

        by_name = self.client.get(reverse("finished-bom-packaging"), {"q": "pe"})
        self.assertEqual(by_name.status_code, 200)
        body = by_name.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["warehouse_code"], "K090150001")
        self.assertEqual(body["results"][0]["name"], "PE袋")
        self.assertEqual(body["results"][0]["plants"], ["3011", "3099"])

        by_plant = self.client.get(reverse("finished-bom-packaging"), {"werks": "3011"})
        self.assertEqual(
            [row["warehouse_code"] for row in by_plant.json()["results"]],
            ["K090150001"],
        )
        self.assertEqual(by_plant.json()["results"][0]["plants"], ["3011", "3099"])

        listed = self.client.get(reverse("finished-bom-packaging"))
        codes = [row["warehouse_code"] for row in listed.json()["results"]]
        self.assertIn("K090150001", codes)
        self.assertIn("K090150002", codes)
        self.assertNotIn("A090150001", codes)

    def test_publish_writes_the_packaging_line(self):
        RawMaterial.objects.create(
            name="PE袋", warehouse_code="K090150011", category=self.raw_type,
        )
        with patch("app_material.services.finished_bom_publish.create_bom") as create:
            create.return_value = [{"type": "S", "text": "成功"}]
            response = self.client.post(
                reverse("finished-bom-publish"),
                data={
                    "formula_id": self.version.pk,
                    "werks": "3011",
                    "stlan": "1",
                    "stlal": "01",
                    "bmeng": "1000",
                    "datuv": "2026-10-26",
                    "mode": "create",
                    "packaging_code": "K090150011",
                    "packaging_qty": "2",
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        line = create.call_args.kwargs["lines"][-1]
        self.assertEqual(line["postp"], "L")
        self.assertEqual(line["meins"], "PC")
        self.assertEqual(line["idnrk"], "K090150011")
        self.assertEqual(line["menge"], "2.000")

    def test_unknown_packaging_is_rejected_before_sap(self):
        with patch("app_material.services.finished_bom_publish.create_bom") as create:
            response = self.client.post(
                reverse("finished-bom-publish"),
                data={
                    "formula_id": self.version.pk,
                    "werks": "3011",
                    "stlan": "1",
                    "stlal": "01",
                    "bmeng": "1000",
                    "datuv": "2026-10-26",
                    "mode": "create",
                    "packaging_code": "K090159999",
                    "packaging_qty": "1",
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")
        create.assert_not_called()

    def test_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("finished_bom_sync"))
        self.assertEqual(response.status_code, 302)

    def test_page_renders_standalone_shell(self):
        response = self.client.get(reverse("finished_bom_sync"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("成品 BOM 发布 / 下架", html)
        self.assertIn("finished_bom_sync.js", html)
        self.assertNotIn("{% verbatim %}", html)
        self.assertIn("csrftoken", response.cookies)

    def test_page_prefills_sap_code_from_the_material_link(self):
        response = self.client.get(reverse("finished_bom_sync"), {"sap_code": "A02009000163"})
        self.assertContains(response, 'window.__FINISHED_BOM_SAP_CODE__ = "A02009000163"')

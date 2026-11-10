"""CRM 目录 API：服务端密钥、已发布材料、文档不走媒体直链。"""
import tempfile
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from app_attachment.models import Attachment
from app_material.models.material import (
    ApplicationScenario,
    MaterialCharacteristic,
    MaterialDataPoint,
    MaterialLibrary,
    MaterialProcessingCondition,
    MaterialType,
    MetricCategory,
    TestConfig,
)
from app_user.services.service_api_key import create_service_api_key

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.key, self.token = create_service_api_key("CRM 官网")
        self.category = MaterialType.objects.create(name="PA66")
        self.scenario = ApplicationScenario.objects.create(name="汽车")
        self.characteristic = MaterialCharacteristic.objects.create(name="耐热")
        self.published = MaterialLibrary.objects.create(
            grade_name="PUB-1",
            manufacturer="华东基地",
            sap_material_code="SAP-PUB-1",
            category=self.category,
            is_published=True,
            description="已发布",
            flammability="V-0",
            material_color_name="哑光黑",
            pantone_code="PANTONE 19-4052",
            rgb_value="#1A1A1A",
        )
        self.published.scenarios.add(self.scenario)
        self.published.characteristics.add(self.characteristic)
        self.hidden = MaterialLibrary.objects.create(
            grade_name="HID-1",
            manufacturer="华东基地",
            sap_material_code="SAP-HID-1",
            category=self.category,
            is_published=False,
        )
        metric = MetricCategory.objects.create(name="机械", order=1)
        config = TestConfig.objects.create(
            category=metric, name="拉伸强度", standard="ISO 527", unit="MPa",
        )
        MaterialDataPoint.objects.create(
            material=self.published, test_config=config, value=Decimal("80.000"),
            min_value=Decimal("70.000"), max_value=Decimal("90.000"),
        )
        attachment = Attachment(
            content_type=ContentType.objects.get_for_model(self.published),
            object_id=self.published.pk,
            category="TDS",
        )
        attachment.file.save("pub-1.pdf", ContentFile(b"%PDF-1.4 test"), save=True)
        self.attachment = attachment

    def auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_missing_wrong_and_expired_keys_are_401(self):
        response = self.client.get("/api/catalog/v1/materials/")
        self.assertEqual(response.status_code, 401)

        self.client.credentials(HTTP_AUTHORIZATION="Bearer cat_wrong")
        self.assertEqual(self.client.get("/api/catalog/v1/materials/").status_code, 401)

        _, expired = create_service_api_key(
            "过期", expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
        self.assertEqual(self.client.get("/api/catalog/v1/nav-tree/").status_code, 401)

    def test_list_search_and_filter_only_published(self):
        self.auth()
        response = self.client.get("/api/catalog/v1/materials/", {"search": "PUB"})
        self.assertEqual(response.status_code, 200)
        names = [row["grade_name"] for row in response.data["results"]]
        self.assertEqual(names, ["PUB-1"])

        filtered = self.client.get(
            "/api/catalog/v1/materials/", {"scenarios": self.scenario.pk},
        )
        self.assertEqual(
            [row["grade_name"] for row in filtered.data["results"]],
            ["PUB-1"],
        )
        row = response.data["results"][0]
        self.assertEqual(row["sap_material_code"], "SAP-PUB-1")
        self.assertEqual(row["flammability"], "V-0")
        self.assertEqual(row["material_color_name"], "哑光黑")
        self.assertEqual(row["pantone_code"], "PANTONE 19-4052")
        self.assertEqual(row["rgb_value"], "#1A1A1A")
        self.assertNotIn("processing_condition", row)
        self.assertNotIn("creator", row)

    def test_detail_includes_properties_and_api_download_url(self):
        self.auth()
        response = self.client.get(f"/api/catalog/v1/materials/{self.published.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["grouped_properties"][0]["category_name"], "机械",
        )
        file_url = response.data["file_tds"]
        self.assertIn(f"/api/catalog/v1/materials/{self.published.pk}/download/tds/", file_url)
        self.assertNotIn("/media/", file_url)
        self.assertIsNone(response.data["file_msds"])
        self.assertIsNone(response.data["file_rohs"])
        self.assertNotIn("file_ul", response.data)
        self.assertIsNone(response.data["processing_condition"])
        item = response.data["grouped_properties"][0]["items"][0]
        self.assertEqual(item["min_value"], "70.000")
        self.assertEqual(item["max_value"], "90.000")
        self.assertEqual(item["min_value_text"], "")
        self.assertEqual(item["max_value_text"], "")

        MaterialProcessingCondition.objects.create(
            material=self.published,
            melt_temp_value="220℃",
            melt_temp_range="210℃ - 230℃",
        )
        again = self.client.get(f"/api/catalog/v1/materials/{self.published.pk}/")
        self.assertEqual(again.data["processing_condition"]["melt_temp_value"], "220℃")
        self.assertEqual(again.data["processing_condition"]["melt_temp_range"], "210℃ - 230℃")
        self.assertEqual(again.data["processing_condition"]["pre_dry_value"], "")

    def test_unpublished_detail_and_bad_download_are_404(self):
        self.auth()
        hidden = self.client.get(f"/api/catalog/v1/materials/{self.hidden.pk}/")
        self.assertEqual(hidden.status_code, 404)
        missing = self.client.get(
            f"/api/catalog/v1/materials/{self.hidden.pk}/download/tds/",
        )
        self.assertEqual(missing.status_code, 404)
        bad_type = self.client.get(
            f"/api/catalog/v1/materials/{self.published.pk}/download/other/",
        )
        self.assertEqual(bad_type.status_code, 404)

    def test_download_streams_file(self):
        self.auth()
        response = self.client.get(
            f"/api/catalog/v1/materials/{self.published.pk}/download/tds/",
        )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content)
        self.assertTrue(body.startswith(b"%PDF-1.4"))

    def _save_tds(self, content, version):
        attachment = Attachment(
            content_type=ContentType.objects.get_for_model(self.published),
            object_id=self.published.pk,
            category="TDS",
            version=version,
        )
        attachment.file.save(f"v{version}.pdf", ContentFile(content), save=True)
        return attachment

    def test_download_prefers_highest_version_then_newest(self):
        self.auth()
        older = timezone.now() - timedelta(days=2)
        newer = timezone.now() - timedelta(days=1)
        low = self._save_tds(b"low-version", version=1)
        high = self._save_tds(b"high-version", version=2)
        Attachment.objects.filter(pk=low.pk).update(uploaded_at=newer)
        Attachment.objects.filter(pk=high.pk).update(uploaded_at=older)

        url = f"/api/catalog/v1/materials/{self.published.pk}/download/tds/"
        higher = self.client.get(url)
        self.assertEqual(b"".join(higher.streaming_content), b"high-version")

        same_old = self._save_tds(b"same-old", version=3)
        same_new = self._save_tds(b"same-new", version=3)
        Attachment.objects.filter(pk=same_old.pk).update(uploaded_at=older)
        Attachment.objects.filter(pk=same_new.pk).update(uploaded_at=newer)
        latest = self.client.get(url)
        self.assertEqual(b"".join(latest.streaming_content), b"same-new")

    def test_nav_tree_counts_only_published(self):
        self.auth()
        response = self.client.get("/api/catalog/v1/nav-tree/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "汽车")
        self.assertEqual(response.data[0]["count"], 1)
        self.assertEqual(response.data[0]["types"][0]["name"], "PA66")
        self.assertEqual(
            response.data[0]["types"][0]["characteristics"][0]["name"], "耐热",
        )
        self.assertIsNone(response.data[0]["background"])
        self.assertIsNone(response.data[0]["types"][0]["background"])
        self.assertIsNone(
            response.data[0]["types"][0]["characteristics"][0]["background"],
        )

    def _save_background(self, parent, filename, content):
        attachment = Attachment(
            content_type=ContentType.objects.get_for_model(parent),
            object_id=parent.pk,
            category="BACKGROUND",
        )
        attachment.file.save(filename, ContentFile(content), save=True)
        return attachment

    def test_nav_tree_background_is_catalog_url_not_media(self):
        self.auth()
        self._save_background(self.scenario, "scene.jpg", b"jpg-scene")
        self._save_background(self.category, "type.png", b"png-type")
        self._save_background(self.characteristic, "char.webp", b"webp-char")

        response = self.client.get("/api/catalog/v1/nav-tree/")
        scene = response.data[0]["background"]
        type_url = response.data[0]["types"][0]["background"]
        char_url = response.data[0]["types"][0]["characteristics"][0]["background"]
        self.assertIn(f"/api/catalog/v1/background/scenario/{self.scenario.pk}/", scene)
        self.assertIn(f"/api/catalog/v1/background/type/{self.category.pk}/", type_url)
        self.assertIn(
            f"/api/catalog/v1/background/characteristic/{self.characteristic.pk}/",
            char_url,
        )
        self.assertNotIn("/media/", scene)
        self.assertTrue(scene.startswith("http"))

        image = self.client.get(f"/api/catalog/v1/background/scenario/{self.scenario.pk}/")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(b"".join(image.streaming_content), b"jpg-scene")

        guest = APIClient()
        self.assertEqual(
            guest.get(f"/api/catalog/v1/background/scenario/{self.scenario.pk}/").status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/catalog/v1/background/scenario/999999/").status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/catalog/v1/background/nope/1/").status_code, 404)

        # 主数据在，但当前没有任何已发布材料用到它，仍然可以取图
        spare = ApplicationScenario.objects.create(name="备用")
        self._save_background(spare, "spare.jpg", b"spare")
        spare_image = self.client.get(f"/api/catalog/v1/background/scenario/{spare.pk}/")
        self.assertEqual(spare_image.status_code, 200)

        # 后缀不对的文件不出现在树上，取图也是 404
        unused = ApplicationScenario.objects.create(name="未使用")
        self._save_background(unused, "note.pdf", b"%PDF")
        self.assertEqual(
            self.client.get(f"/api/catalog/v1/background/scenario/{unused.pk}/").status_code,
            404,
        )
        names = [row["name"] for row in self.client.get("/api/catalog/v1/nav-tree/").data]
        self.assertNotIn("未使用", names)

        scene_file = Attachment.objects.get(
            object_id=self.scenario.pk, category="BACKGROUND",
        )
        scene_file.is_deleted = True
        scene_file.save()
        refreshed = self.client.get("/api/catalog/v1/nav-tree/")
        self.assertIsNone(refreshed.data[0]["background"])

    @override_settings(ALLOWED_HOSTS=["a.example.com", "b.example.com", "testserver"])
    def test_background_url_follows_the_request_host(self):
        self.auth()
        self._save_background(self.scenario, "scene.jpg", b"jpg-scene")
        first = self.client.get("/api/catalog/v1/nav-tree/", HTTP_HOST="a.example.com")
        second = self.client.get("/api/catalog/v1/nav-tree/", HTTP_HOST="b.example.com")
        self.assertTrue(
            first.data[0]["background"].startswith(
                "http://a.example.com/api/catalog/v1/background/scenario/",
            )
        )
        self.assertTrue(
            second.data[0]["background"].startswith(
                "http://b.example.com/api/catalog/v1/background/scenario/",
            )
        )

    def test_background_upload_rejects_non_image_and_second_file(self):
        from django.contrib.auth import get_user_model
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.urls import reverse

        from app_attachment.forms import AttachmentUploadForm
        from app_attachment.registry import get_attachment_config_for_model

        config = get_attachment_config_for_model(ApplicationScenario)
        pdf_form = AttachmentUploadForm(
            {"category": "BACKGROUND", "version": 1},
            {"file": SimpleUploadedFile("a.pdf", b"%PDF")},
            config=config,
        )
        self.assertFalse(pdf_form.is_valid())
        self.assertNotIn(".pdf", AttachmentUploadForm(config=config).fields["file"].widget.attrs["accept"])

        library_form = AttachmentUploadForm(
            config=get_attachment_config_for_model(MaterialLibrary),
        )
        self.assertIn(".pdf", library_form.fields["file"].widget.attrs["accept"])

        admin = get_user_model().objects.create_superuser(
            "bg-admin", "bg-admin@example.com", "pass-12345",
        )
        client = APIClient()
        client.force_login(admin)
        content_type = ContentType.objects.get_for_model(self.scenario)
        url = reverse(
            "attachment:upload",
            kwargs={"content_type_id": content_type.id, "object_id": self.scenario.pk},
        )
        uploaded = {
            "category": "BACKGROUND",
            "version": 1,
        }
        first = client.post(url, {
            **uploaded,
            "file": SimpleUploadedFile("bg.jpg", b"one", content_type="image/jpeg"),
        })
        self.assertEqual(first.status_code, 302)
        stored = Attachment.objects.filter(
            content_type=content_type,
            object_id=self.scenario.pk,
            category="BACKGROUND",
            is_deleted=False,
        )
        self.assertEqual(stored.count(), 1)
        second = client.post(url, {
            **uploaded,
            "file": SimpleUploadedFile("bg2.png", b"two", content_type="image/png"),
        })
        self.assertEqual(second.status_code, 302)
        self.assertEqual(stored.count(), 1)

    def test_background_panel_only_on_dimension_edit(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from app_material.views.Characteristic import CharacteristicCreateView
        from app_material.views.MaterialType import MaterialTypeCreateView
        from app_material.views.Scenario import ScenarioCreateView

        admin = get_user_model().objects.create_superuser(
            "bg-page", "bg-page@example.com", "pass-12345",
        )
        client = APIClient()
        client.force_login(admin)
        edit = client.get(reverse("type_edit", kwargs={"pk": self.category.pk}))
        self.assertEqual(edit.status_code, 200)
        self.assertContains(edit, "附件管理")
        metric = MetricCategory.objects.get(name="机械")
        other = client.get(reverse("metric_category_edit", kwargs={"pk": metric.pk}))
        self.assertEqual(other.status_code, 200)
        self.assertNotContains(other, "附件管理")

        for view_cls, obj, name in (
            (MaterialTypeCreateView, self.category, "type_edit"),
            (ScenarioCreateView, self.scenario, "scenario_edit"),
            (CharacteristicCreateView, self.characteristic, "characteristic_edit"),
        ):
            view = view_cls()
            view.object = obj
            self.assertEqual(view.get_success_url(), reverse(name, kwargs={"pk": obj.pk}))

    def test_retired_handbook_routes_are_gone(self):
        self.assertEqual(self.client.get("/catalog/").status_code, 404)
        self.assertEqual(self.client.get("/api/external/materials/").status_code, 404)
        self.assertEqual(self.client.get("/api/catalog/materials/").status_code, 404)

"""CAD 在线预览：preview_kind 判断 + viewer 路由权限。"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app_attachment.forms import AttachmentUploadForm
from app_attachment.models import Attachment
from app_form_management.models import FormSubmission, FormTemplate

User = get_user_model()


class AttachmentPreviewKindTests(SimpleTestCase):
    """不落库：只根据 file.name 判断预览类型与图标。"""

    def _att(self, name):
        att = Attachment()
        att.file.name = name
        return att

    def test_stp_is_cad3d(self):
        att = self._att('upload/part.stp')
        self.assertEqual(att.extension, 'stp')
        self.assertEqual(att.preview_kind, 'cad3d')
        self.assertTrue(att.can_preview_3d)
        self.assertEqual(att.file_icon_class, 'ti ti-box')

    def test_step_and_iges_variants(self):
        for name in ('a.step', 'b.igs', 'c.iges', 'd.IGES', 'e.STP'):
            att = self._att(name)
            self.assertEqual(att.preview_kind, 'cad3d', name)
            self.assertTrue(att.can_preview_3d, name)

    def test_pdf_has_no_preview(self):
        att = self._att('doc.pdf')
        self.assertEqual(att.preview_kind, '')
        self.assertFalse(att.can_preview_3d)
        self.assertEqual(att.file_icon_class, 'ti ti-file')

    def test_image_icon(self):
        att = self._att('pic.PNG')
        self.assertTrue(att.is_image)
        self.assertFalse(att.can_preview_3d)
        self.assertEqual(att.file_icon_class, 'ti ti-photo')

    def test_empty_file_has_no_preview(self):
        att = Attachment()
        self.assertEqual(att.preview_kind, '')
        self.assertFalse(att.can_preview_3d)


class AttachmentUploadAcceptTests(SimpleTestCase):
    def test_accept_includes_iges(self):
        accept = AttachmentUploadForm._get_accept_types()
        self.assertIn('.stp', accept)
        self.assertIn('.step', accept)
        self.assertIn('.igs', accept)
        self.assertIn('.iges', accept)


class AttachmentViewerTests(TestCase):
    """viewer 与 download 共用 token 权限；不支持的类型 404。"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')
        self.other = User.objects.create_user(
            username='other', email='other@test.dev', password='x')
        self.template = FormTemplate.objects.create(
            name='测试表单',
            form_config=[],
            form_option={},
        )
        self.submission = FormSubmission.objects.create(
            template=self.template,
            submitted_by=self.admin,
            form_data={},
            status='DRAFT',
        )
        self.ct = ContentType.objects.get_for_model(FormSubmission)

    def _create(self, filename, content=b'ISO-10303-21;'):
        return Attachment.objects.create(
            content_type=self.ct,
            object_id=self.submission.pk,
            file=SimpleUploadedFile(filename, content, content_type='application/octet-stream'),
            uploader=self.admin,
            category='OTHER',
        )

    def test_invalid_token_is_403(self):
        self.client.force_login(self.admin)
        url = reverse('attachment:viewer', kwargs={'token': 'not-a-uuid'})
        self.assertEqual(self.client.get(url).status_code, 403)
        url = reverse('attachment:viewer', kwargs={
            'token': '00000000-0000-0000-0000-000000000000',
        })
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_anonymous_is_403(self):
        att = self._create('part.stp')
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_no_permission_is_403(self):
        att = self._create('part.stp')
        self.client.force_login(self.other)
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_pdf_is_404(self):
        att = self._create('spec.pdf', b'%PDF-1.4')
        self.client.force_login(self.admin)
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_cad_superuser_gets_200(self):
        att = self._create('housing.stp')
        self.client.force_login(self.admin)
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cad-preview-page-stage')
        download_url = reverse(
            'attachment:download', kwargs={'token': att.download_token})
        self.assertContains(response, 'data-cad-url="' + download_url + '"')
        self.assertContains(response, 'cad_preview.js')
        self.assertContains(response, 'data-cad-tree-panel')
        self.assertContains(response, 'data-cad-action="view"')
        self.assertContains(response, 'data-cad-view="left"')
        self.assertContains(response, 'data-cad-view="right"')
        self.assertContains(response, 'data-cad-view="back"')
        self.assertContains(response, 'data-cad-view="bottom"')
        self.assertContains(response, 'data-cad-action="view-roll"')
        self.assertContains(response, 'data-cad-action="ortho"')
        self.assertContains(response, 'data-cad-action="screenshot"')
        self.assertContains(response, 'data-cad-action="xray"')
        self.assertContains(response, 'data-cad-action="place-pivot"')
        self.assertContains(response, 'data-cad-action="pivot-selected"')
        self.assertContains(response, 'data-cad-action="section"')
        self.assertContains(response, 'data-cad-action="explode"')
        self.assertContains(response, 'data-cad-action="explode-selected"')
        self.assertContains(response, 'data-cad-action="explode-style"')
        self.assertContains(response, 'data-cad-explode="even"')
        self.assertContains(response, 'data-cad-explode="bin"')
        self.assertContains(response, 'data-cad-action="explode-center"')
        self.assertContains(response, 'data-cad-section-panel')
        self.assertContains(response, 'data-cad-explode-panel')
        self.assertContains(response, 'cad-preview-body')
        self.assertNotContains(response, 'page-wrapper')
        self.assertNotContains(response, 'includes/sidebar.html')
        self.assertNotContains(response, 'htmx.min.js')

    def test_iges_superuser_gets_200(self):
        att = self._create('mold.iges')
        self.client.force_login(self.admin)
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_deleted_attachment_is_403(self):
        att = self._create('part.stp')
        att.is_deleted = True
        att.save(update_fields=['is_deleted'])
        self.client.force_login(self.admin)
        url = reverse('attachment:viewer', kwargs={'token': att.download_token})
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_download_still_works(self):
        att = self._create('part.stp', b'step-bytes')
        self.client.force_login(self.admin)
        url = reverse('attachment:download', kwargs={'token': att.download_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'step-bytes')

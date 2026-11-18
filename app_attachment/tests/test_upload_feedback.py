"""上传失败时，HTMX 弹窗里要能看到提示，而不是错误页或下一次整页的 message。"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import DataError
from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse

from app_attachment.validators import MAX_UPLOAD_BYTES
from app_attachment.views import _UPLOAD_FORM_ERROR, _UPLOAD_SAVE_ERROR
from app_form_management.models import FormSubmission, FormTemplate

User = get_user_model()


class UploadFailureFeedbackTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')
        self.client.force_login(self.admin)
        template = FormTemplate.objects.create(
            name='测试表单',
            form_config=[],
            form_option={},
        )
        self.submission = FormSubmission.objects.create(
            template=template,
            submitted_by=self.admin,
            form_data={},
            status='DRAFT',
        )
        ct = ContentType.objects.get_for_model(FormSubmission)
        self.url = reverse('attachment:upload', kwargs={
            'content_type_id': ct.pk,
            'object_id': self.submission.pk,
        })

    def test_upload_form_advertises_size_limit(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'data-max-bytes="{MAX_UPLOAD_BYTES}"')
        self.assertContains(response, '最大 50MB')
        self.assertNotContains(response, 'type="submit" class="btn btn-primary" disabled')
        self.assertIn(
            "js/apps/app_attachment/upload_size.js' %}?v=2",
            get_template('base.html').template.source,
        )

    def test_invalid_htmx_post_shows_error_in_modal(self):
        response = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _UPLOAD_FORM_ERROR)
        self.assertContains(response, '上传附件')
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_save_error_stays_in_modal(self):
        payload = {
            'file': SimpleUploadedFile('note.pdf', b'%PDF-1.4', content_type='application/pdf'),
            'category': 'OTHER',
            'version': 1,
        }
        with patch('app_attachment.views.Attachment.save', side_effect=DataError('simulated')):
            response = self.client.post(self.url, payload, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _UPLOAD_SAVE_ERROR)
        self.assertNotContains(response, 'simulated')
        self.assertNotContains(response, 'DataError')
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_invalid_plain_post_still_redirects_with_message(self):
        response = self.client.post(self.url, HTTP_REFERER='/after-upload/')
        self.assertRedirects(response, '/after-upload/', fetch_redirect_response=False)
        self.assertIn(_UPLOAD_FORM_ERROR, [str(message) for message in get_messages(response.wsgi_request)])

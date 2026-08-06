import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse

from app_attachment.models import Attachment
from app_form_management.models import FormSubmission, FormTemplate

User = get_user_model()


class SubmissionAttachmentCascadeTest(TestCase):
    """删除草稿/提交时，联动清理其附件（数据库行 + 物理文件）。"""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='x')
        self.template = FormTemplate.objects.create(
            name='测试表单',
            form_config=[],
            form_option={},
            created_by=None,
        )
        self.submission = FormSubmission.objects.create(
            template=self.template,
            submitted_by=self.user,
            form_data={},
            status='DRAFT',
        )

    def _create_attachment(self):
        ct = ContentType.objects.get_for_model(FormSubmission)
        return Attachment.objects.create(
            content_type=ct,
            object_id=self.submission.pk,
            file=SimpleUploadedFile('draft.txt', b'draft content', content_type='text/plain'),
            uploader=self.user,
            category='OTHER',
            group_key='field:enclosure',
        )

    def test_delete_submission_removes_attachments(self):
        att = self._create_attachment()
        file_path = att.file.name
        self.assertEqual(
            Attachment.objects.filter(
                content_type=ContentType.objects.get_for_model(FormSubmission),
                object_id=self.submission.pk,
            ).count(),
            1,
        )
        self.submission.delete()
        # 附件行已联动删除，不再孤儿
        self.assertFalse(Attachment.objects.filter(pk=att.pk).exists())
        # 物理文件也被清理（django-cleanup / post_delete 信号）
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists(file_path))

    def test_delete_submission_with_no_attachments(self):
        # 无附件时删除不应报错
        self.submission.delete()
        self.assertFalse(FormSubmission.objects.filter(pk=self.submission.pk).exists())

    def test_unrelated_attachment_kept(self):
        # 其他提交的附件不受影响
        other = FormSubmission.objects.create(
            template=self.template,
            submitted_by=self.user,
            form_data={},
            status='DRAFT',
        )
        att = self._create_attachment()
        ct = ContentType.objects.get_for_model(FormSubmission)
        other_att = Attachment.objects.create(
            content_type=ct,
            object_id=other.pk,
            file=SimpleUploadedFile('other.txt', b'other', content_type='text/plain'),
            uploader=self.user,
            category='OTHER',
        )
        self.submission.delete()
        self.assertFalse(Attachment.objects.filter(pk=att.pk).exists())
        self.assertTrue(Attachment.objects.filter(pk=other_att.pk).exists())


class FormUploadDeleteHardDeleteTest(TestCase):
    """表单上传组件点击删除：真实删除数据库行 + 磁盘文件（非软删除）。"""

    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='x')
        self.template = FormTemplate.objects.create(
            name='测试表单',
            form_config=[],
            form_option={},
            created_by=None,
        )
        self.submission = FormSubmission.objects.create(
            template=self.template,
            submitted_by=self.user,
            form_data={},
            status='DRAFT',
        )
        self.client.force_login(self.user)

    def _create_attachment_with_form_data(self):
        ct = ContentType.objects.get_for_model(FormSubmission)
        att = Attachment.objects.create(
            content_type=ct,
            object_id=self.submission.pk,
            file=SimpleUploadedFile('report.txt', b'file data', content_type='text/plain'),
            uploader=self.user,
            category='OTHER',
            group_key='field:enclosure',
        )
        url = reverse('attachment:download', kwargs={'token': str(att.download_token)})
        self.submission.form_data = {'enclosure': [{'url': url, 'name': att.display_name}]}
        self.submission.save(update_fields=['form_data'])
        return att

    def test_delete_removes_row_and_physical_file(self):
        att = self._create_attachment_with_form_data()
        file_path = att.file.name

        resp = self.client.post(
            reverse('form_upload_delete'),
            data=json.dumps({'token': str(att.download_token)}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('status'), 'success')

        # 数据库行已硬删除
        self.assertFalse(Attachment.objects.filter(pk=att.pk).exists())
        # 磁盘文件已真实删除
        self.assertFalse(default_storage.exists(file_path))
        # form_data 中对应条目已移除
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.form_data.get('enclosure'), [])
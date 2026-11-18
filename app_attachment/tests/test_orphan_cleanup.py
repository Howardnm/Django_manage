"""Admin 清理 upload_files/ 中没有 Attachment 记录的文件。"""
import os
import shutil
import tempfile
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from app_attachment.cleanup import delete_orphan_files, scan_orphan_files
from app_attachment.models import Attachment
from app_form_management.models import FormSubmission, FormTemplate

User = get_user_model()


class OrphanCleanupTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@test.dev', password='x', is_staff=True)
        self.viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='app_attachment',
            codename='view_attachment',
        ))
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
        self.url = reverse('admin:app_attachment_attachment_orphan_files')
        self.old_mtime = time.time() - 3600

    def _create(self, filename, content=b'kept'):
        return Attachment.objects.create(
            content_type=self.ct,
            object_id=self.submission.pk,
            file=SimpleUploadedFile(filename, content),
            uploader=self.admin,
            category='OTHER',
        )

    def _write(self, relative, content=b'orphan', mtime=None):
        full = os.path.join(self.media_root, *relative.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as saved:
            saved.write(content)
        os.utime(full, (mtime or self.old_mtime, mtime or self.old_mtime))
        return full

    def _names(self, items):
        return {item['name'] for item in items}

    def test_recorded_and_soft_deleted_files_are_kept(self):
        live = self._create('live.pdf')
        deleted = self._create('soft.pdf')
        deleted.is_deleted = True
        deleted.save(update_fields=['is_deleted'])
        deletable, recent = scan_orphan_files()
        names = self._names(deletable) | self._names(recent)
        self.assertNotIn(live.file.name, names)
        self.assertNotIn(deleted.file.name, names)

    def test_old_file_under_upload_root_is_listed_logo_is_not(self):
        orphan = 'upload_files/loose/2000-01-01/old.bin'
        logo = 'oem/logos/logo.png'
        self._write(orphan)
        self._write(logo)
        deletable, recent = scan_orphan_files()
        self.assertIn(orphan, self._names(deletable))
        self.assertNotIn(logo, self._names(deletable) | self._names(recent))

    def test_recent_orphan_is_skipped_and_survives_post(self):
        recent_name = 'upload_files/loose/new.bin'
        full = self._write(recent_name, mtime=time.time())
        deletable, recent = scan_orphan_files()
        self.assertIn(recent_name, self._names(recent))
        self.assertNotIn(recent_name, self._names(deletable))

        self.client.force_login(self.admin)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(os.path.exists(full))

    def test_post_deletes_old_orphan_and_empty_dirs_only(self):
        live = self._create('live.pdf')
        orphan = 'upload_files/loose/2000-01-01/old.bin'
        self._write(orphan)
        self.client.force_login(self.admin)
        response = self.client.post(self.url)
        self.assertRedirects(response, self.url)
        self.assertFalse(os.path.exists(os.path.join(self.media_root, *orphan.split('/'))))
        self.assertFalse(os.path.isdir(os.path.join(
            self.media_root, 'upload_files', 'loose')))
        self.assertTrue(os.path.exists(os.path.join(self.media_root, *live.file.name.split('/'))))
        self.assertTrue(os.path.isdir(os.path.join(self.media_root, 'upload_files')))
        self.assertEqual(Attachment.objects.count(), 1)

    def test_delete_leaves_upload_root_when_nothing_remains(self):
        self._write('upload_files/only/old.txt')
        result = delete_orphan_files()
        self.assertEqual(result['deleted'], 1)
        root = os.path.join(self.media_root, 'upload_files')
        self.assertTrue(os.path.isdir(root))
        self.assertEqual(os.listdir(root), [])

    def test_viewer_can_open_but_not_delete(self):
        full = self._write('upload_files/loose/old.bin')
        self.client.force_login(self.viewer)
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'upload_files/loose/old.bin')
        self.assertNotContains(page, '确认删除')
        denied = self.client.post(self.url)
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(os.path.exists(full))

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_changelist_links_to_cleanup(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:app_attachment_attachment_changelist'))
        self.assertContains(response, self.url)

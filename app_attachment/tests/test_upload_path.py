"""存储路径长度，以及写库失败时不留下磁盘文件。"""
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models.sql.compiler import SQLInsertCompiler
from django.db.utils import DataError
from django.test import TestCase, override_settings

from app_attachment.models import Attachment
from app_form_management.models import FormSubmission, FormTemplate

User = get_user_model()


class AttachmentUploadPathTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')
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

    def _create(self, filename, content=b'x'):
        return Attachment.objects.create(
            content_type=self.ct,
            object_id=self.submission.pk,
            file=SimpleUploadedFile(filename, content),
            uploader=self.admin,
            category='OTHER',
        )

    def test_field_max_length_is_255(self):
        self.assertEqual(Attachment._meta.get_field('file').max_length, 255)

    def test_stem_longer_than_60_is_kept(self):
        stem = '甲' * 61
        att = self._create(stem + '.PDF')
        self.assertLessEqual(len(att.file.name), 255)
        self.assertTrue(att.file.name.endswith(stem + '.PDF'))
        self.assertNotIn('\\', att.file.name)
        self.assertEqual(att.display_name, stem + '.PDF')
        self.assertTrue(default_storage.exists(att.file.name))

    def test_stem_is_truncated_to_100(self):
        stem = '乙' * 101
        att = self._create(stem + '.pdf')
        stored = att.file.name.rsplit('/', 1)[-1]
        self.assertEqual(stored, ('乙' * 100) + '.pdf')
        self.assertLessEqual(len(att.file.name), 255)
        self.assertEqual(att.display_name, stem + '.pdf')
        self.assertTrue(default_storage.exists(att.file.name))

    def test_insert_error_removes_new_file(self):
        written = []
        storage = Attachment._meta.get_field('file').storage
        real_save = storage.save

        def spy(name, content, max_length=None):
            stored = real_save(name, content, max_length=max_length)
            written.append(stored)
            return stored

        orig = SQLInsertCompiler.execute_sql

        def execute_sql(compiler, returning_fields=None):
            if compiler.query.model is Attachment:
                compiler.returning_fields = returning_fields
                list(compiler.as_sql())
                raise DataError('simulated')
            return orig(compiler, returning_fields)

        with patch.object(storage, 'save', spy), \
                patch.object(SQLInsertCompiler, 'execute_sql', execute_sql):
            with self.assertRaises(DataError):
                with transaction.atomic():
                    self._create('orphan.pdf')

        self.assertEqual(len(written), 1)
        self.assertFalse(storage.exists(written[0]))

    def test_atomic_rollback_removes_new_file(self):
        stored = {}
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                att = self._create('rollback.pdf')
                stored['name'] = att.file.name
                self.assertTrue(default_storage.exists(att.file.name))
                raise RuntimeError('rollback')
        self.assertFalse(default_storage.exists(stored['name']))

    def test_successful_save_keeps_file(self):
        att = self._create('kept.pdf')
        self.assertTrue(default_storage.exists(att.file.name))

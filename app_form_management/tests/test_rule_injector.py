from django.test import SimpleTestCase

from app_form_management.rule_injector import inject_upload_config


def upload_rule(auto_upload_absent=True, auto_upload=None):
    props = {}
    if not auto_upload_absent:
        props['autoUpload'] = auto_upload
    return {
        'type': 'upload',
        'field': 'enclosure',
        'title': '附件',
        'props': props,
    }


class AutoUploadConfigTest(SimpleTestCase):
    def test_defaults_to_true_when_absent(self):
        configured = inject_upload_config([upload_rule()], 1, 'csrf')
        self.assertIs(configured[0]['props']['autoUpload'], True)

    def test_preserves_designer_false(self):
        configured = inject_upload_config(
            [upload_rule(auto_upload_absent=False, auto_upload=False)], 1, 'csrf')
        self.assertIs(configured[0]['props']['autoUpload'], False)

    def test_preserves_designer_true(self):
        configured = inject_upload_config(
            [upload_rule(auto_upload_absent=False, auto_upload=True)], 1, 'csrf')
        self.assertIs(configured[0]['props']['autoUpload'], True)

    def test_injects_on_change_tracking_field(self):
        configured = inject_upload_config([upload_rule()], 1, 'csrf')
        on_change = configured[0]['props']['onChange']
        self.assertTrue(on_change.startswith('$FNX:'))
        # 记录该字段的文件列表，供前端 flush 使用
        self.assertIn('__fcPendingUploads__', on_change)
        self.assertIn('"enclosure"', on_change)

    def test_does_not_mutate_original_rules(self):
        rule = upload_rule()
        inject_upload_config([rule], 1, 'csrf')
        # 深拷贝：原规则不应被注入
        self.assertNotIn('autoUpload', rule['props'])
        self.assertNotIn('action', rule['props'])


class BeforeRemoveLogicTest(SimpleTestCase):
    def setUp(self):
        cfg = inject_upload_config([upload_rule()], 1, 'csrf')
        self.before_remove = cfg[0]['props']['beforeRemove']

    def test_pending_file_removed_locally(self):
        # 待上传文件：有 raw 但无服务器 URL → 直接返回 true，不走后端删除
        self.assertIn(
            'var isPending = !!(file && file.raw) && !(file.url'
            ' && file.url.indexOf("/attachment/download/") > -1);',
            self.before_remove,
        )
        self.assertIn('if (isPending) return true;', self.before_remove)

    def test_uploaded_file_still_backend_delete(self):
        # 已上传文件：仍调用后端删除端点
        self.assertIn('fetch("/forms/api/upload/delete/"', self.before_remove)
        self.assertIn('if (!token) return false;', self.before_remove)

    def test_not_editable_no_before_remove(self):
        cfg = inject_upload_config([upload_rule()], 1, 'csrf', is_editable=False)
        self.assertNotIn('beforeRemove', cfg[0]['props'])
        self.assertTrue(cfg[0]['props'].get('disabled'))
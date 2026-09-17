"""附件模板标签的查询数回归。

三个标签的历史行为：

    attachment_url    每次调用独立查一次库 —— TDS/MSDS/RoHS 三件套 = 3 条查询
    attachment_panel  为渲染一个数量徽标查一次附件表，而列表其实由 HTMX 另拉
    attachment_prime  不存在 —— 列表页每行各自查一次，页内查询数 = 行数

现在：三件套共用一次装载（缓存在父对象实例上）；列表页行循环前用
attachment_prime 一次查完；数量徽标改由列表片段以 hx-swap-oob 回填。
"""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import connection
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from app_attachment.models import Attachment
from app_material.models import MaterialLibrary, MaterialType
from app_raw_material.models import RawMaterial, RawMaterialType

User = get_user_model()


def _at(year, month, day):
    """带时区的日期 —— Attachment.uploaded_at 是 auto_now_add，只能靠回写控制排序。"""
    return timezone.make_aware(datetime(year, month, day))


class AttachmentTagTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='uploader', password='x')
        cls.material_type = MaterialType.objects.create(name='工程塑料')
        cls.material = MaterialLibrary.objects.create(
            grade_name='TAG-TEST', sap_material_code='A07000',
            category=cls.material_type, creator=cls.user)
        # 预热 ContentType 缓存，避免它混进被计数的查询里
        cls.ct = ContentType.objects.get_for_model(MaterialLibrary)
        cls.raw_ct = ContentType.objects.get_for_model(RawMaterial)
        cls.rm_type = RawMaterialType.objects.create(name='树脂')

    # ── 造数据 ──

    def _make_material(self, name):
        return MaterialLibrary.objects.create(
            grade_name=name, sap_material_code=f'A{abs(hash(name)) % 100000}',
            category=self.material_type, creator=self.user)

    def _make_raw_material(self, name):
        return RawMaterial.objects.create(name=name, category=self.rm_type)

    def _attachment(self, category, target=None, uploaded_at=None, is_deleted=False):
        target = target if target is not None else self.material
        att = Attachment.objects.create(
            content_type=ContentType.objects.get_for_model(target),
            object_id=target.pk, file='x.pdf',
            category=category, uploader=self.user, is_deleted=is_deleted)
        # uploaded_at 是 auto_now_add，只能回写
        Attachment.objects.filter(pk=att.pk).update(
            uploaded_at=uploaded_at or _at(2026, 1, 1))
        att.refresh_from_db()
        return att

    # ── 渲染 ──

    def _render(self, objects, categories, prime=False):
        """渲染「对每个对象依次取这些分类的 URL」，返回 (渲染结果, 查询数)。

        模板源码用拼接而非 f-string —— 模板语法本身全是花括号。
        """
        calls = ''
        for i, category in enumerate(categories):
            calls += ("{% attachment_url o '" + category + "' as u" + str(i)
                      + " %}{{ u" + str(i) + " }}|")
        source = '{% load attachment_tags %}'
        if prime:
            source += '{% attachment_prime objects %}'
        source += '{% for o in objects %}' + calls + '{% endfor %}'

        with CaptureQueriesContext(connection) as ctx:
            html = Template(source).render(Context({'objects': objects}))
        return html, len(ctx.captured_queries)

    def _render_urls(self, *categories, prime=False):
        """单个对象（详情页形状）的便捷包装。"""
        return self._render([self.material], categories, prime=prime)

    def _url_of(self, attachment):
        return reverse('attachment:download',
                       kwargs={'token': attachment.download_token})


class AttachmentUrlTests(AttachmentTagTestBase):
    def test_three_categories_share_one_query(self):
        """三件套原本各查一次（3 条），现在共用一次装载。"""
        self._attachment('TDS')
        self._attachment('MSDS')
        self._attachment('RoHS')

        urls, queries = self._render_urls('TDS', 'MSDS', 'RoHS')
        urls = [u for u in urls.split('|') if u]

        self.assertEqual(len(urls), 3)
        self.assertEqual(queries, 1, f'三个分类应只查一次库，实际 {queries} 次')

    def test_returns_empty_string_for_missing_category(self):
        tds = self._attachment('TDS')

        urls, _ = self._render_urls('TDS', 'RoHS')
        urls = [u for u in urls.split('|') if u]

        self.assertEqual(urls, [self._url_of(tds)])  # RoHS 无附件 → 空串被过滤掉

    def test_picks_newest_attachment_of_category(self):
        """与旧实现 `.first()`（Meta ordering = -uploaded_at）口径一致：取最新那条。"""
        self._attachment('TDS', uploaded_at=_at(2026, 1, 1))
        newest = self._attachment('TDS', uploaded_at=_at(2026, 6, 1))

        urls, _ = self._render_urls('TDS')
        urls = [u for u in urls.split('|') if u]

        self.assertEqual(urls, [self._url_of(newest)])

    def test_soft_deleted_attachment_is_ignored(self):
        self._attachment('TDS', uploaded_at=_at(2026, 6, 1), is_deleted=True)
        alive = self._attachment('TDS', uploaded_at=_at(2026, 1, 1))

        urls, _ = self._render_urls('TDS')
        urls = [u for u in urls.split('|') if u]

        self.assertEqual(urls, [self._url_of(alive)])


class AttachmentPrimeTests(AttachmentTagTestBase):
    """列表页形状：N 行 × 三件套，用 attachment_prime 把查询数压成常数。"""

    CATEGORIES = ('TDS', 'MSDS', 'RoHS')

    def _rows(self, count):
        rows = []
        for i in range(count):
            material = self._make_material(f'PRIME-{i}')
            for category in self.CATEGORIES:
                self._attachment(category, target=material)
            rows.append(material)
        return rows

    def _fresh_rows(self):
        """重新取一遍实例 —— 预热过的实例会跳过装载，跨次测量必须换新的。"""
        return list(MaterialLibrary.objects.filter(
            grade_name__startswith='PRIME-').order_by('grade_name'))

    def test_prime_collapses_per_row_queries(self):
        self._rows(5)

        unprimed, unprimed_q = self._render(self._fresh_rows(), self.CATEGORIES)
        primed, primed_q = self._render(self._fresh_rows(), self.CATEGORIES, prime=True)

        self.assertEqual(unprimed_q, 5, '不预载时应为「每行一次」')
        self.assertEqual(primed_q, 1, f'预载后应只查一次库，实际 {primed_q} 次')
        self.assertEqual(unprimed, primed, '预载不能改变渲染结果')

    def test_prime_groups_mixed_parent_types(self):
        """一页混多种父对象时按 ContentType 分组，每类各一条查询。"""
        materials = self._rows(2)
        raws = []
        for i in range(2):
            rm = self._make_raw_material(f'RM-PRIME-{i}')
            self._attachment('TDS', target=rm)
            raws.append(rm)

        _, queries = self._render(materials + raws, ('TDS',), prime=True)

        self.assertEqual(queries, 2, f'两种父对象应各查一次，实际 {queries} 次')

    def test_prime_handles_paginator_page(self):
        """模板传的是 page_obj（各列表视图都分页），Page 也要能直接迭代。"""
        self._rows(3)
        page = Paginator(MaterialLibrary.objects.filter(
            grade_name__startswith='PRIME-'), 2).page(1)
        len(page)  # 先触发分页切片查询，把它排除在统计之外

        _, queries = self._render(page, self.CATEGORIES, prime=True)

        self.assertEqual(queries, 1)

    def test_prime_is_idempotent_within_a_render(self):
        """同一批对象重复调用不该重复查库。"""
        rows = self._rows(3)
        source = ('{% load attachment_tags %}{% attachment_prime objects %}'
                  '{% attachment_prime objects %}')
        with CaptureQueriesContext(connection) as ctx:
            Template(source).render(Context({'objects': rows}))
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_prime_covers_objects_without_attachments(self):
        """没有附件的行也要挂上空映射，否则它会退回「按需装载」再查一次。"""
        rows = self._rows(2)
        rows.append(self._make_material('PRIME-EMPTY'))

        html, queries = self._render(rows, ('TDS',), prime=True)

        self.assertEqual(queries, 1)
        self.assertEqual(html.count('|'), 3)  # 3 行都渲染了（空 URL 渲染成空串）


class AttachmentPanelTests(AttachmentTagTestBase):
    def _render_panel(self):
        tpl = Template('{% load attachment_tags %}{% attachment_panel obj %}')
        with CaptureQueriesContext(connection) as ctx:
            html = tpl.render(Context({'obj': self.material}))
        return html, len(ctx.captured_queries)

    def test_panel_does_not_touch_attachment_table(self):
        """面板渲染不查附件表 —— 数量徽标由列表片段的 OOB 回填。"""
        self._attachment('TDS')

        html, queries = self._render_panel()

        self.assertEqual(queries, 0, f'面板不应查库，实际 {queries} 次')
        self.assertIn(f'attachment-count-{self.ct.id}-{self.material.pk}', html)

    def test_badge_id_matches_between_panel_and_list_fragment(self):
        """OOB 靠 id 匹配：两边 id 一旦不一致，徽标会静默留空。"""
        self._attachment('TDS')
        panel_html, _ = self._render_panel()

        list_html = render_to_string('apps/app_attachment/_file_list.html', {
            'attachments': Attachment.objects.filter(
                content_type=self.ct, object_id=self.material.pk, is_deleted=False),
            'config': None,
            'content_type_id': self.ct.id,
            'object_id': self.material.pk,
        })

        badge_id = f'attachment-count-{self.ct.id}-{self.material.pk}'
        self.assertIn(f'id="{badge_id}"', panel_html)
        self.assertIn(f'id="{badge_id}"', list_html)
        self.assertIn('hx-swap-oob', list_html)
        self.assertIn('>1<', list_html)  # 列表片段带上真实数量

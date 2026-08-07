"""审批/填写页只读控制的回归测试。

覆盖单据只读算法（window.FCReadonly，见
static/js/apps/app_form_management/form_readonly.js）以及后端步骤方法对
嵌套（表格/分组）字段的处理。

JS 只读算法在浏览器端执行，本测试以 Python 忠实转写同一算法（下述
READONLY_TYPES / step_of / set_readonly / apply_readonly 与 JS 文件一一对应），
对「组件类型 × 放置位置(顶层/表格内/行列内/分组内) × 单/多步骤 × 设计器是否已禁用」
进行矩阵式验证；若 JS 文件改动，需同步更新此处转写。
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_form_management.models import FormTemplate

User = get_user_model()

# ── 与 form_readonly.js 的 FC_READONLY_TYPES 保持一致 ──
READONLY_TYPES = [
    'input', 'textarea', 'password', 'inputNumber',
    'datePicker', 'dateRange', 'timePicker', 'timeRange',
]
# 不支持 readonly、必须回退到 disabled 的组件
NON_READONLY_TYPES = [
    'select', 'radio', 'checkbox', 'switch', 'slider', 'upload',
    'cascader', 'rate', 'color', 'treeSelect', 'editor', 'signaturePad',
]


# ── 忠实转写 form_readonly.js 的算法 ──

def step_of(r):
    props = r.get('props') or {}
    step = props.get('step')
    return int(step) if step is not None else 1


def set_readonly(r):
    props = r.setdefault('props', {})
    r['$required'] = False
    r['validate'] = None
    if props.get('disabled') is True:          # 设计器已禁用 → 保持 disabled
        return
    if r.get('type') in READONLY_TYPES:
        props['readonly'] = True
    else:
        props['disabled'] = True


def apply_readonly(rules, is_readonly):
    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get('field') and is_readonly(r):
            set_readonly(r)
        for key in ('children', 'control'):
            child = r.get(key)
            if isinstance(child, list):
                apply_readonly(child, is_readonly)


# ── 构造规则辅助 ──

def field(type_, field, step=None, disabled=None, required=True, readonly=None):
    props = {}
    if step is not None:
        props['step'] = step
    if disabled is not None:
        props['disabled'] = disabled
    if readonly is not None:
        props['readonly'] = readonly
    rule = {'type': type_, 'field': field, 'title': field, 'props': props}
    if required:
        rule['$required'] = True
        rule['validate'] = [{'required': True}]
    return rule


def table(children, step=None):
    props = {'rule': {'row': 2, 'col': 2}}
    if step is not None:
        props['step'] = step
    return {'type': 'fcTable', 'props': props, 'children': children}


def row(children):
    return {'type': 'fcRow', 'props': {}, 'children': children}


def col(children):
    return {'type': 'col', 'props': {}, 'children': children}


def group(children):
    return {'type': 'group', 'field': 'grp', 'props': {'title': '分组'}, 'control': children}


def subform(children):
    return {'type': 'subForm', 'field': 'sub', 'props': {}, 'control': children}


def only_editable(rules):
    """返回所有仍可编辑（未设 readonly/disabled）的『数据字段』名。

    group/subForm 虽有 field 但属容器，其自身是否可编辑不影响数据，不计入。
    """
    out = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get('field') and r.get('type') not in ('group', 'subForm'):
            props = r.get('props') or {}
            if not props.get('disabled') and not props.get('readonly'):
                out.append(r['field'])
        for key in ('children', 'control'):
            child = r.get(key)
            if isinstance(child, list):
                out.extend(only_editable(child))
    return out


def find_rule(rules, field):
    """在整个规则树中查找指定 field 的规则。"""
    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get('field') == field:
            return r
        for key in ('children', 'control'):
            child = r.get(key)
            if isinstance(child, list):
                hit = find_rule(child, field)
                if hit:
                    return hit
    return None


# ══════════════════════════════════════════════════════════════════
# 1. 单字段只读控制（set_readonly）
# ══════════════════════════════════════════════════════════════════

class SetReadonlyTest(TestCase):
    def test_readonly_types_get_readonly(self):
        for t in READONLY_TYPES:
            r = field(t, t + '_f')
            set_readonly(r)
            self.assertTrue(r['props'].get('readonly'), f'{t} 应设 readonly')
            self.assertNotIn('disabled', r['props'])

    def test_non_readonly_types_fallback_to_disabled(self):
        for t in NON_READONLY_TYPES:
            r = field(t, t + '_f')
            set_readonly(r)
            self.assertTrue(r['props'].get('disabled'), f'{t} 应回退 disabled')
            self.assertNotIn('readonly', r['props'])

    def test_designer_disabled_is_preserved(self):
        # 设计器已设 disabled → 保持 disabled，不转 readonly
        for t in READONLY_TYPES:
            r = field(t, t + '_f', disabled=True)
            set_readonly(r)
            self.assertTrue(r['props'].get('disabled'), f'{t} 应保持 disabled')
            self.assertNotIn('readonly', r['props'])

    def test_removes_required_and_validate(self):
        r = field('input', 'x', required=True)
        set_readonly(r)
        self.assertFalse(r['$required'])
        self.assertIsNone(r.get('validate'))

    def test_editable_field_keeps_required(self):
        # is_readonly 返回 False 的字段不应被触碰
        rules = [field('input', 'x', required=True)]
        apply_readonly(rules, lambda r: False)
        self.assertTrue(rules[0]['$required'])
        self.assertIsNotNone(rules[0].get('validate'))
        self.assertNotIn('readonly', rules[0]['props'])
        self.assertNotIn('disabled', rules[0]['props'])


# ══════════════════════════════════════════════════════════════════
# 2. 递归 + 放置位置（组件在顶层 / 表格内 / 行列内 / 分组内）
# ══════════════════════════════════════════════════════════════════

class ApplyReadonlyNestingTest(TestCase):
    def _assert_all_readonly(self, rules):
        for t in READONLY_TYPES + NON_READONLY_TYPES:
            rule = find_rule(rules, t + '_f')
            self.assertIsNotNone(rule, f'{t} 字段应存在')
            props = rule['props']
            self.assertTrue(props.get('readonly') or props.get('disabled'),
                            f'{t} 字段应被设为只读/禁用')

    def test_every_component_type_at_every_nesting(self):
        """所有组件类型 × 所有放置位置，在「全部只读」模式下都应被锁定。"""
        for position in ('top', 'table', 'rowcol', 'group', 'subform'):
            rules = {
                'top': [field(t, t + '_f') for t in READONLY_TYPES + NON_READONLY_TYPES],
                'table': [table([field(t, t + '_f') for t in READONLY_TYPES + NON_READONLY_TYPES])],
                'rowcol': [row([col([field(t, t + '_f') for t in READONLY_TYPES + NON_READONLY_TYPES])])],
                'group': [group([field(t, t + '_f') for t in READONLY_TYPES + NON_READONLY_TYPES])],
                'subform': [subform([field(t, t + '_f') for t in READONLY_TYPES + NON_READONLY_TYPES])],
            }[position]
            apply_readonly(rules, lambda r: True)
            self._assert_all_readonly(rules)

    def test_table_nested_fields_are_locked(self):
        """核心回归：表格容器内的字段此前从不会被禁用，现在必须被锁定。"""
        rules = [table([field('input', 'tbl_a'), field('select', 'tbl_b')])]
        apply_readonly(rules, lambda r: True)
        self.assertTrue(find_rule(rules, 'tbl_a')['props'].get('readonly'))
        self.assertTrue(find_rule(rules, 'tbl_b')['props'].get('disabled'))
        self.assertEqual(only_editable(rules), [])

    def test_layout_container_itself_is_not_treated_as_field(self):
        # fcTable/fcRow/col 无 field，不应被 set_readonly（不会被标记为可编辑字段）
        rules = [table([field('input', 'a')])]
        apply_readonly(rules, lambda r: True)
        tbl = rules[0]
        self.assertNotIn('readonly', tbl['props'])
        self.assertNotIn('disabled', tbl['props'])


# ══════════════════════════════════════════════════════════════════
# 3. 单步骤 / 多步骤填写控制
# ══════════════════════════════════════════════════════════════════

class StepControlTest(TestCase):
    def test_single_step_all_editable(self):
        """单步骤：全部字段保持可编辑（isReadonly 恒为 False）。"""
        rules = [field('input', 'a', step=1), table([field('select', 'b', step=1)])]
        apply_readonly(rules, lambda r: False)
        self.assertEqual(only_editable(rules), ['a', 'b'])

    def test_multi_step_step1_editable_others_readonly(self):
        """多步骤填写页：仅步骤1可编辑，其余步骤（含表格内、行列内、分组内）只读。"""
        rules = [
            field('input', 's1_top', step=1, required=True),
            field('select', 's2_top', step=2),
            field('input', 's3_top', step=3),
            table([
                field('input', 'tbl_s1', step=1, required=True),
                field('select', 'tbl_s2', step=2),
                field('inputNumber', 'tbl_s3', step=3),
            ]),
            row([col([field('input', 'col_s2', step=2)])]),
            group([field('select', 'grp_s2', step=2)]),
        ]
        # 模拟填写页 workflowRestricted：仅步骤1可编辑（isReadonly = step != 1）
        apply_readonly(rules, lambda r: step_of(r) != 1)

        self.assertEqual(only_editable(rules), ['s1_top', 'tbl_s1'])
        # 步骤1字段保留必填
        self.assertTrue(find_rule(rules, 's1_top')['$required'])
        self.assertTrue(find_rule(rules, 'tbl_s1')['$required'])
        # 步骤2/3 字段被锁定且移除必填/校验
        for f in ('s2_top', 's3_top', 'tbl_s2', 'tbl_s3', 'col_s2', 'grp_s2'):
            rule = find_rule(rules, f)
            self.assertTrue(rule['props'].get('readonly') or rule['props'].get('disabled'),
                            f'{f} 应被锁定')
            self.assertFalse(rule['$required'])
            self.assertIsNone(rule.get('validate'))

    def test_approval_step_control(self):
        """审批页：当前审批人只编辑其步骤，其余步骤只读。"""
        rules = [
            field('input', 's1', step=1, required=True),
            field('select', 's2', step=2),
            table([
                field('input', 'tbl_s1', step=1, required=True),
                field('select', 'tbl_s2', step=2),
            ]),
        ]
        current_step = 2
        apply_readonly(rules, lambda r: step_of(r) != current_step)
        self.assertEqual(only_editable(rules), ['s2', 'tbl_s2'])
        self.assertTrue(find_rule(rules, 's1')['props'].get('readonly'))
        self.assertTrue(find_rule(rules, 'tbl_s1')['props'].get('readonly'))
        self.assertTrue(find_rule(rules, 'tbl_s2')['$required'])


# ══════════════════════════════════════════════════════════════════
# 4. 后端集成：填写页 GET 渲染（单/多步骤，含嵌套字段）
# ══════════════════════════════════════════════════════════════════

def _template(name, form_config, with_workflow=False):
    cfg = {'enabled': False}
    return FormTemplate.objects.create(
        name=name,
        form_config=form_config,
        form_option={'codeConfig': cfg},
        created_by=None,
    )


class FillPageRenderTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='x')
        self.client.force_login(self.user)

    def _get_fill(self, template):
        return self.client.get(reverse('form_submission_fill', kwargs={'template_pk': template.pk}))

    def test_single_step_fill(self):
        t = _template('单步', [field('input', 'a', step=1)])
        resp = self._get_fill(t)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['is_multi_step'] is False)
        self.assertFalse(resp.context['workflow_restricted'])
        groups = json.loads(resp.context['step_groups_json'])
        self.assertEqual([g['step'] for g in groups], [1])
        # 页面引入了共享只读脚本
        self.assertContains(resp, 'form_readonly.js')

    def test_multi_step_fill_with_nested_fields(self):
        t = _template('多步', [
            field('input', 's1', step=1),
            field('select', 's2', step=2),
            table([field('input', 'tbl_s2', step=2)]),
        ])
        resp = self._get_fill(t)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['is_multi_step'])
        groups = json.loads(resp.context['step_groups_json'])
        # 表格内字段的步骤也参与分组
        self.assertEqual([g['step'] for g in groups], [1, 2])
        # form_config 注入完整的嵌套规则
        config = json.loads(resp.context['form_config_json'])
        tbl = next(r for r in config if r.get('type') == 'fcTable')
        self.assertEqual(tbl['children'][0]['field'], 'tbl_s2')

    def test_multi_step_with_workflow_is_restricted(self):
        from app_workflow.models import WorkflowDefinition
        wf = WorkflowDefinition.objects.create(
            name='审批流', bpmn_xml='', is_active=True, created_by=self.user,
        )
        t = FormTemplate.objects.create(
            name='多步+流程', created_by=None,
            form_config=[field('input', 's1', step=1), field('input', 's2', step=2)],
            form_option={'codeConfig': {'enabled': False}},
            workflow=wf,
        )
        resp = self._get_fill(t)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['workflow_restricted'])


# ══════════════════════════════════════════════════════════════════
# 5. 审批详情页渲染（无流程的纯查看，验证模板/脚本引用有效）
# ══════════════════════════════════════════════════════════════════

class SubmissionDetailRenderTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='x')
        self.client.force_login(self.user)

    def test_detail_page_renders_and_loads_shared_readonly_script(self):
        from app_form_management.models import FormSubmission
        t = FormTemplate.objects.create(
            name='审批查看', created_by=None,
            form_config=[table([field('input', 'tbl_a', step=1)]), field('select', 's1', step=1)],
            form_option={'codeConfig': {'enabled': False}},
        )
        sub = FormSubmission.objects.create(
            template=t, submitted_by=self.user, form_data={'tbl_a': 'x'}, status='SUBMITTED',
        )
        resp = self.client.get(reverse('form_submission_detail', kwargs={'pk': sub.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'form_readonly.js')
        self.assertContains(resp, 'submission_detail.js')
        # 全部只读（无流程 → can_edit_step 为 False → 静态 JS detail-config 驱动 FCReadonly 全只读）
        detail_config = json.loads(resp.context['detail_config_json'])
        self.assertIs(detail_config['canEditStep'], False)
        injected = json.loads(resp.context['form_config_json'])
        self.assertEqual(injected[0]['type'], 'fcTable')
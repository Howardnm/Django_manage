"""
app_form_management 伪数据生成器

业务逻辑：
  - 从 init/form_configs/*.json 读取表单模板配置，创建 FormTemplate
  - 每个模板的 steps 与 BPMN camunda:formStep 严格对齐
  - FormSubmission 通过 GenericForeignKey 关联 Project，SUBMITTED 触发 WorkflowService.start()
"""

import json
import random
from pathlib import Path
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from ._base import FakeContext, fake, pick_one, pick

# form_config JSON 文件目录
_FORM_DIR = Path(__file__).resolve().parent.parent / 'form_configs'


def _load_form_specs():
    """扫描 init/form_configs/*.json，返回 form_spec 列表"""
    specs = []
    for json_file in sorted(_FORM_DIR.glob('*.json')):
        data = json.loads(json_file.read_text(encoding='utf-8'))
        data['_filename'] = json_file.name
        specs.append(data)
    return specs


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[14/16] Creating form templates & submissions...")

    from app_form_management.models import FormTemplate, FormSubmission
    from app_project.models import Project

    # =====================================================================
    # 1. 从 JSON 文件导入表单模板
    # =====================================================================
    wf_map = {wf.name: wf for wf in ctx.workflow_defs}
    form_specs = _load_form_specs()

    form_templates = []
    for spec in form_specs:
        wf_name = spec.get('workflow_name')
        workflow = wf_map.get(wf_name) if wf_name else None

        t, _ = FormTemplate.objects.update_or_create(
            name=spec['name'],
            defaults={
                'group': spec.get('group', ''),
                'description': spec.get('description', f"from init/form_configs/{spec['_filename']}"),
                'form_config': spec.get('form_config', []),
                'form_option': spec.get('form_option', {}),
                'workflow': workflow,
                'created_by': ctx.admin,
            },
        )
        form_templates.append(t)
        steps = len(t.step_groups)
        wf_mark = f"+wf={wf_name}" if workflow else "(no workflow)"
        print(f"    {spec['_filename']} -> [{t.name}] steps={steps} {wf_mark}")

    ctx.form_templates = form_templates

    # =====================================================================
    # 2. 创建 FormSubmission + 触发 WorkflowService.start()
    # =====================================================================
    from app_workflow.services import WorkflowService

    project_ct = ContentType.objects.get_for_model(Project)
    wf_templates = [t for t in form_templates if t.workflow_id]
    simple_templates = [t for t in form_templates if not t.workflow_id]

    # --- 为每个工作流模板创建 SUBMITTED 提交（触发真实审批流程） ---
    submitted_count = 0
    for tpl in wf_templates:
        for i in range(2):
            project = pick_one(ctx.projects)
            submitter = project.manager or pick_one(ctx.rnd_users)

            # 从 form_config 字段名生成匹配的表单数据
            field_keys = [f.get('field') for f in (tpl.form_config or []) if f.get('field')]
            form_data = _generate_form_data(tpl.name, field_keys, project)

            submission = FormSubmission.objects.create(
                template=tpl,
                content_type=project_ct,
                object_id=project.pk,
                submitted_by=submitter,
                form_data=form_data,
                status='SUBMITTED',
                remark='auto-generated from fake data',
            )

            try:
                instance = WorkflowService.start(
                    definition=tpl.workflow,
                    started_by=submitter,
                    related_object=submission,
                    context_data={'form_data': form_data},
                )
                submission.workflow_instance = instance
                submission.save(update_fields=['workflow_instance'])
                submitted_count += 1
            except Exception as e:
                print(f"    [WARN] workflow start failed for [{tpl.name}]: {e}")

    # --- 无工作流的简单表单提交（DRAFT + SUBMITTED 混合） ---
    for tpl in simple_templates:
        for _ in range(3):
            field_keys = [f.get('field') for f in (tpl.form_config or []) if f.get('field')]
            FormSubmission.objects.create(
                template=tpl,
                content_type=project_ct,
                object_id=pick_one(ctx.projects).pk,
                submitted_by=pick_one(ctx.all_internal),
                form_data=_generate_form_data(tpl.name, field_keys, None),
                status=pick_one(['DRAFT', 'SUBMITTED', 'SUBMITTED']),
            )

    print(f"  form_templates={len(form_templates)} (w/ workflow={len(wf_templates)}), "
          f"submissions={FormSubmission.objects.count()}, "
          f"workflow_instances_from_forms={submitted_count}")


# ===========================================================================
# 辅助函数
# ===========================================================================

def _generate_form_data(template_name, field_keys, project):
    """根据模板类型和字段列表生成匹配的表单数据"""
    from django.utils import timezone

    base = {}

    # 按模板名称匹配字段 → 值映射
    if '研发评审' in template_name:
        base.update({
            'project_name': project.name if project else fake.text(15),
            'plan_desc': fake.text(40),
            'priority': pick_one(['high', 'medium', 'low']),
            'tech_feasibility': fake.text(30),
            'resource_needs': f"{random.randint(2, 5)}人 / {random.randint(1, 3)}台",
            'estimated_days': str(random.randint(10, 60)),
            'process_feasibility': fake.text(25),
            'market_assessment': fake.text(25),
        })
    elif '量产放行' in template_name:
        base.update({
            'product_name': project.name if project else fake.text(15),
            'test_report_no': f"TR-{timezone.now().strftime('%Y%m%d')}",
            'qa_result': pick_one(['pass', 'conditional', 'pass']),
            'capacity_assessment': str(round(random.uniform(5, 50), 1)),
            'material_status': fake.text(30),
            'release_opinion': fake.text(20),
        })
    elif '异常处理' in template_name:
        base.update({
            'exception_type': pick_one(['quality', 'process', 'equipment', 'material', 'other']),
            'exception_desc': f"试生产中发生异常：{fake.text(30)}",
            'root_cause': fake.text(35),
            'responsible_party': pick_one(['研发部', '工艺部', '供应链', '设备厂商']),
            'decision': fake.text(20),
        })
    elif '来料检验' in template_name:
        base.update({
            'title': f"来料检验-{random.randint(100, 999)}",
            'supplier_name': fake.company(),
            'material_batch': f"LOT-{timezone.now().strftime('%Y%m%d')}-{random.randint(100, 999):03d}",
            'content': fake.text(20),
            'inspector': fake.name(),
            'inspect_date': f"{random.randint(2024, 2026)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            'result': pick_one(['pass', 'pass', 'pass', 'fail']),
        })

    # 只保留 form_config 中确实存在的字段
    return {k: v for k, v in base.items() if k in field_keys}

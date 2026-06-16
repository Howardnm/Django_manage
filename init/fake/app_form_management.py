"""
app_form_management 伪数据生成器

业务逻辑：
  - FormTemplate：表单模板（form-create-designer JSON 配置），可关联 WorkflowDefinition
  - FormSubmission：表单提交，通过 GenericForeignKey 关联业务对象（此处关联 Project）
"""

import random
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from ._base import FakeContext, fake, pick_one, COUNT_FORM_TEMPLATES


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[11/13] Creating form templates & submissions...")

    from app_form_management.models import FormTemplate, FormSubmission

    form_templates = []
    for name, group in [
        ("来料检验单", "质检"),
        ("出货检验单", "质检"),
        ("实验记录表", "研发"),
        ("客户投诉单", "售后"),
    ]:
        t, _ = FormTemplate.objects.get_or_create(
            name=name,
            defaults={
                'group': group,
                'description': f"{name} - auto generated",
                'form_config': [
                    {'type': 'text', 'label': 'title', 'key': 'title'},
                    {'type': 'textarea', 'label': 'content', 'key': 'content'},
                ],
                'workflow': (
                    pick_one(ctx.workflow_defs)
                    if random.random() < 0.5
                    else None
                ),
                'created_by': ctx.admin,
            },
        )
        form_templates.append(t)
    ctx.form_templates = form_templates

    # --- FormSubmission（关联到 Project） ---
    from app_project.models import Project
    project_ct = ContentType.objects.get_for_model(Project)
    for _ in range(8):
        FormSubmission.objects.create(
            template=pick_one(form_templates),
            content_type=project_ct,
            object_id=pick_one(ctx.projects).pk,
            submitted_by=pick_one(ctx.all_internal),
            form_data={
                'title': f"submission-{random.randint(100, 999)}",
                'content': fake.text(30),
            },
            status=pick_one(['DRAFT', 'SUBMITTED', 'SUBMITTED']),
        )

    print(f"  form_templates={len(form_templates)}, "
          f"submissions={FormSubmission.objects.count()}")

import logging
import re

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import FormSubmission, FormTemplate

logger = logging.getLogger(__name__)

# 日期格式预设（UI 下拉选项，存储 strftime 模式）
CODE_DATE_FORMATS = [
    ('%Y%m%d', 'YYYYMMDD  例:20260806'),
    ('%y%m%d', 'YYMMDD  例:260806'),
    ('%Y-%m-%d', 'YYYY-MM-DD  例:2026-08-06'),
    ('%Y-%m', 'YYYY-MM  例:2026-08'),
    ('%Y', 'YYYY  例:2026'),
]


def get_template_code_config(template):
    """读取模板的编码配置（form_option['codeConfig']），未启用返回 None。"""
    option = template.form_option or {}
    cfg = option.get('codeConfig') or {}
    if not cfg.get('enabled'):
        return None
    return cfg


def generate_form_code(template, seq):
    """根据模板编码配置 + 序号，渲染出编码字符串。"""
    cfg = get_template_code_config(template)
    if not cfg:
        return ''
    prefix = cfg.get('prefix', '')
    date_fmt = cfg.get('dateFormat', '%Y%m%d')
    separator = cfg.get('separator', '-')
    seq_len = int(cfg.get('seqLength', 3) or 3)
    code = prefix
    if date_fmt:
        code += timezone.localdate().strftime(date_fmt)
    code += separator + str(seq).zfill(seq_len)
    return code


def assign_submission_code(submission):
    """为提交记录赋业务编码（仅首次提交生成；配置了 targetField 时始终回写字段值）。

    取号在 transaction.atomic() 内锁定模板行，串行化同一模板的序号，避免并发竞态。
    返回是否成功赋码。
    """
    template = submission.template
    cfg = get_template_code_config(template)
    if not cfg:
        return False

    target_field = cfg.get('targetField')

    if not submission.code:
        with transaction.atomic():
            # 锁定模板行，串行化同模板取号
            FormTemplate.objects.select_for_update().get(pk=template.pk)
            date_fmt = cfg.get('dateFormat', '%Y%m%d')
            bucket_prefix = (
                (cfg.get('prefix', '') or '') +
                timezone.localdate().strftime(date_fmt) +
                (cfg.get('separator', '-') or '-')
            )
            last = (FormSubmission.objects
                    .filter(code__startswith=bucket_prefix)
                    .order_by('code').last())
            seq = 1
            if last and last.code:
                m = re.search(r'(\d+)$', last.code)
                if m:
                    seq = int(m.group(1)) + 1
            submission.code = generate_form_code(template, seq)
            submission.save(update_fields=['code'])

    # 配置了写入字段时，把编码回写进 form_data（新赋码与退回修订重提均执行）
    if target_field:
        fd = dict(submission.form_data or {})
        fd[target_field] = submission.code
        submission.form_data = fd
        submission.save(update_fields=['form_data'])

    return True


class FormSubmissionService:
    """Stateless service for creating and finding FormSubmissions via GFK."""

    def create_or_update(self, template, target_object, submitted_by, form_data,
                         status='SUBMITTED', remark=''):
        """Create or update a FormSubmission bound to `target_object` via GFK."""
        ct = ContentType.objects.get_for_model(target_object)
        existing = FormSubmission.objects.filter(
            template=template,
            content_type=ct,
            object_id=target_object.pk,
            submitted_by=submitted_by,
            status='DRAFT',
        ).first()

        if existing:
            existing.form_data = form_data
            existing.remark = remark
            existing.status = status
            existing.save()
            if status == 'SUBMITTED':
                assign_submission_code(existing)
            return existing
        else:
            submission = FormSubmission.objects.create(
                template=template,
                target_object=target_object,
                submitted_by=submitted_by,
                form_data=form_data,
                status=status,
                remark=remark,
            )
            if status == 'SUBMITTED':
                assign_submission_code(submission)
            return submission

    def get_draft(self, template, target_object, submitted_by):
        """Return the DRAFT submission for (template, target, user), or None."""
        ct = ContentType.objects.get_for_model(target_object)
        return FormSubmission.objects.filter(
            template=template,
            content_type=ct,
            object_id=target_object.pk,
            submitted_by=submitted_by,
            status='DRAFT',
        ).first()

submission_service = FormSubmissionService()

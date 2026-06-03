from django.db import models


class TrialProductionConfig(models.Model):
    """排产全局配置 — 单例 (pk=1)"""
    workflow_definition = models.ForeignKey(
        'app_workflow.WorkflowDefinition', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="审批流程定义",
        help_text="排产单进入挤出任务前需要经过的审批流程")

    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "排产全局配置"
        verbose_name_plural = "排产全局配置"

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]

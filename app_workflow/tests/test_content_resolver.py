"""回归测试：_batch_resolve_content_objects 迁移到 utils.py 后行为不变。

该函数从 app_workflow/views.py 迁入 app_workflow/utils.py，
供 InitiatedInstanceListView 及个人工作台复用。原视图层无测试覆盖，此处补充。
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from app_project.models import Project
from app_workflow.models import WorkflowDefinition, WorkflowInstance
from app_workflow.utils import _batch_resolve_content_objects

User = get_user_model()


class BatchResolveContentObjectsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='wf_user', password='x')
        self.project = Project.objects.create(
            name='关联流程项目', manager=self.user,
        )
        self.defn = WorkflowDefinition.objects.create(name='审批流程', bpmn_xml='')
        self.ct = ContentType.objects.get_for_model(Project)

    def _instance(self, obj=None):
        kw = dict(definition=self.defn, started_by=self.user)
        if obj is not None:
            kw['content_type'] = ContentType.objects.get_for_model(type(obj))
            kw['object_id'] = obj.pk
        return WorkflowInstance.objects.create(**kw)

    def test_resolves_content_object(self):
        """有关联对象时，_content_object 被正确附加。"""
        inst = self._instance(self.project)
        _batch_resolve_content_objects([inst])
        self.assertEqual(inst._content_object, self.project)

    def test_no_content_type_leaves_empty(self):
        """无 content_type 时不下发查询，_content_object 为空。"""
        inst = self._instance()
        _batch_resolve_content_objects([inst])
        self.assertIsNone(getattr(inst, '_content_object', None))

    def test_mixed_batch_resolves_only_matching(self):
        """批量解析：仅有关联的实例被解析，其余保持为空。"""
        with_obj = self._instance(self.project)
        without_obj = self._instance()
        _batch_resolve_content_objects([with_obj, without_obj])
        self.assertEqual(with_obj._content_object, self.project)
        self.assertIsNone(getattr(without_obj, '_content_object', None))

    def test_empty_list_is_noop(self):
        """空列表调用不报错。"""
        _batch_resolve_content_objects([])
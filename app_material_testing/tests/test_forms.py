"""TestResultMatrixForm validation tests."""
from django.test import TestCase
from django.test.client import RequestFactory
from app_material_testing.forms import TestResultMatrixForm


class TestResultMatrixFormTests(TestCase):
    def test_form_requires_testing_task(self):
        """无 testing_task 时表单应拒绝"""
        form = TestResultMatrixForm({})
        self.assertFalse(form.is_valid())

"""MoldTypeFilter tests."""
from django.test import TestCase

from app_mold_injection.filters import MoldTypeFilter
from app_mold_injection.models import MoldType


class MoldTypeFilterTests(TestCase):
    def setUp(self):
        self.iso_bar = MoldType.objects.create(
            name='拉伸样条模', mold_code='ISO-527',
            mold_type=MoldType.MoldTypeChoices.TEST_SPECIMEN,
            standard=MoldType.Standard.ISO,
            status=MoldType.Status.AVAILABLE,
        )
        self.retired = MoldType.objects.create(
            name='成品壳体模', mold_code='FP-010',
            mold_type=MoldType.MoldTypeChoices.FINISHED_PART,
            standard=MoldType.Standard.GB,
            status=MoldType.Status.RETIRED,
        )

    def _ids(self, data):
        return set(MoldTypeFilter(data, queryset=MoldType.objects.all()).qs.values_list('pk', flat=True))

    def test_empty_returns_all(self):
        self.assertEqual(self._ids({}), {self.iso_bar.pk, self.retired.pk})

    def test_search_by_code_or_name(self):
        self.assertEqual(self._ids({'q': '527'}), {self.iso_bar.pk})
        self.assertEqual(self._ids({'q': '壳体'}), {self.retired.pk})

    def test_status_and_mold_type(self):
        self.assertEqual(
            self._ids({'status': MoldType.Status.RETIRED}),
            {self.retired.pk},
        )
        self.assertEqual(
            self._ids({'mold_type': MoldType.MoldTypeChoices.TEST_SPECIMEN}),
            {self.iso_bar.pk},
        )

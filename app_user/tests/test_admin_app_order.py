"""Admin 首页分组顺序：业务链路在前，清单外分组保持相对顺序。"""

from django.test import SimpleTestCase

from Django_manage.admin_order import ADMIN_APP_ORDER, sort_admin_apps


def _app(label):
    return {"app_label": label, "name": label, "models": [{"name": "z"}, {"name": "a"}]}


class AdminAppOrderTests(SimpleTestCase):
    def test_known_apps_follow_business_chain(self):
        shuffled = [_app(label) for label in reversed(ADMIN_APP_ORDER)]
        labels = [app["app_label"] for app in sort_admin_apps(shuffled)]
        self.assertEqual(labels, list(ADMIN_APP_ORDER))

    def test_unknown_apps_keep_relative_order_after_known(self):
        apps = [
            _app("axes"),
            _app("app_user"),
            _app("authtoken"),
            _app("app_project"),
            _app("app_material"),
        ]
        labels = [app["app_label"] for app in sort_admin_apps(apps)]
        self.assertEqual(
            labels,
            ["app_project", "app_material", "app_user", "axes", "authtoken"],
        )

    def test_model_lists_are_left_untouched(self):
        apps = [_app("app_user"), _app("app_project")]
        ordered = sort_admin_apps(apps)
        self.assertEqual(
            [model["name"] for model in ordered[0]["models"]],
            ["z", "a"],
        )

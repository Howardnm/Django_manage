"""Linux 上预加载 SAP SDK。不加载真实的 .so。"""

import os
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase

from app_sap_services.connection import (
    _SDK_LIBS,
    _SDK_OPTIONAL_LIB,
    _drop_broken_pyrfc,
    _import_pyrfc,
    _preload_sdk_libs,
)
from app_sap_services.exceptions import SAPConnectionError


class SdkPreloadTests(SimpleTestCase):
    def _touch(self, directory, names):
        for name in names:
            with open(os.path.join(directory, name), "wb"):
                pass

    def test_loads_required_libs_then_the_optional_one_before_sapucum(self):
        with tempfile.TemporaryDirectory() as directory:
            self._touch(directory, list(_SDK_LIBS) + [_SDK_OPTIONAL_LIB])
            with patch("app_sap_services.connection.ctypes.CDLL") as load:
                _preload_sdk_libs(directory)

        loaded = [call.args[0] for call in load.call_args_list]
        self.assertEqual(
            [os.path.basename(path) for path in loaded],
            [
                "libicudata.so.50",
                "libicuuc.so.50",
                "libicui18n.so.50",
                "libicudecnumber.so",
                "libsapucum.so",
                "libsapnwrfc.so",
            ],
        )
        self.assertTrue(all(os.path.isabs(path) for path in loaded))
        import ctypes
        self.assertTrue(all(call.kwargs["mode"] is ctypes.RTLD_GLOBAL for call in load.call_args_list))

    def test_skips_the_optional_lib_when_this_sdk_does_not_ship_it(self):
        with tempfile.TemporaryDirectory() as directory:
            self._touch(directory, _SDK_LIBS)
            with patch("app_sap_services.connection.ctypes.CDLL") as load:
                _preload_sdk_libs(directory)

        names = [os.path.basename(call.args[0]) for call in load.call_args_list]
        self.assertNotIn(_SDK_OPTIONAL_LIB, names)
        self.assertEqual(names[-2:], ["libsapucum.so", "libsapnwrfc.so"])

    def test_missing_required_lib_names_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            present = [name for name in _SDK_LIBS if name != "libicudata.so.50"]
            self._touch(directory, present)
            with patch("app_sap_services.connection.ctypes.CDLL") as load:
                with self.assertRaises(SAPConnectionError) as raised:
                    _preload_sdk_libs(directory)

        self.assertIn("libicudata.so.50", str(raised.exception))
        load.assert_not_called()

    def test_load_failure_keeps_the_os_error(self):
        with tempfile.TemporaryDirectory() as directory:
            self._touch(directory, _SDK_LIBS)
            with patch("app_sap_services.connection.ctypes.CDLL", side_effect=OSError("wrong ELF class")):
                with self.assertRaises(SAPConnectionError) as raised:
                    _preload_sdk_libs(directory)

        self.assertIn("wrong ELF class", str(raised.exception))
        self.assertIn("libicudata.so.50", str(raised.exception))


class PyrfcImportTests(SimpleTestCase):
    def test_failed_module_without_connection_is_removed(self):
        import sys
        import types

        fake = types.ModuleType("pyrfc")
        extension = types.ModuleType("pyrfc._cyrfc")
        sys.modules["pyrfc"] = fake
        sys.modules["pyrfc._cyrfc"] = extension
        try:
            _drop_broken_pyrfc()
            self.assertNotIn("pyrfc", sys.modules)
            self.assertNotIn("pyrfc._cyrfc", sys.modules)
        finally:
            sys.modules.pop("pyrfc", None)
            sys.modules.pop("pyrfc._cyrfc", None)

    def test_extension_import_error_keeps_the_original_message(self):
        import sys
        import types

        package = types.ModuleType("pyrfc")
        package.Connection = object()
        extension = types.ModuleType("pyrfc._cyrfc")
        with patch.dict(sys.modules, {"pyrfc": package, "pyrfc._cyrfc": extension}):
            with self.assertRaises(ImportError) as raised:
                _import_pyrfc()

        self.assertIn("pyrfc 扩展加载失败", str(raised.exception))
        self.assertIn("Connection", str(raised.exception))
        self.assertNotIn("ldconfig", str(raised.exception))

"""Verify every flat-module shim exposes the surface CAM-SIMA imports."""

import unittest


class TestCcppCapgenShim(unittest.TestCase):

    def test_capgen_importable(self):
        from ccpp_capgen import capgen, CapDatabase
        self.assertTrue(callable(capgen))
        self.assertTrue(isinstance(CapDatabase, type))


class TestFrameworkEnvShim(unittest.TestCase):

    def test_class_importable(self):
        from framework_env import CCPPFrameworkEnv
        env = CCPPFrameworkEnv(None)
        self.assertIsNone(env.host_files)


class TestCcppStateMachineShim(unittest.TestCase):

    def test_singleton_importable(self):
        from ccpp_state_machine import CCPP_STATE_MACH
        phases = CCPP_STATE_MACH.transitions()
        self.assertIn('run', phases)


class TestParseToolsShim(unittest.TestCase):

    def test_re_exports(self):
        import parse_tools as pt
        for name in ('validate_xml_file', 'read_xml_file',
                     'find_schema_file', 'find_schema_version',
                     'init_log', 'CCPPError', 'ParseInternalError',
                     'ParseObject', 'context_string'):
            self.assertTrue(hasattr(pt, name))

    def test_parse_object_basic_construction(self):
        """``ParseObject`` is now vendored from original capgen (no
        longer a stub).  Verify construction with the original
        signature works and ``filename`` round-trips."""
        import parse_tools as pt
        obj = pt.ParseObject('test.F90', ['line1', 'line2'])
        self.assertEqual(obj.filename, 'test.F90')

    def test_parse_object_curr_line(self):
        """``.curr_line()`` returns ``(line, line_num)`` from the
        provided buffer.  Smoke test that the writable line_num path
        works (capgen's bare ParseContext has read-only line_num,
        which is why the vendor was needed)."""
        import parse_tools as pt
        obj = pt.ParseObject('foobar.F90',
                             ['first line', '## hi mom'],
                             line_start=1)
        line, _ = obj.curr_line()
        self.assertEqual(line, '## hi mom')


class TestMetadataTableShim(unittest.TestCase):

    def test_imports(self):
        import metadata_table as mt
        self.assertTrue(hasattr(mt, 'parse_metadata_file'))
        self.assertTrue(hasattr(mt, 'find_scheme_names'))
        self.assertTrue(hasattr(mt, 'MetadataTable'))


class TestFortranToolsShim(unittest.TestCase):

    def test_fortran_writer_importable(self):
        from fortran_tools import FortranWriter
        self.assertTrue(isinstance(FortranWriter, type))


if __name__ == '__main__':
    unittest.main()

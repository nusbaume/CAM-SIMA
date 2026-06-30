"""Tests for ``capgen_compat._runner`` helpers.

Capgen hardcodes its datatable output to ``<output_root>/datatable.xml``;
CAM-SIMA's ``cam_autogen.py`` reads back from ``ccpp_datatable.xml`` (the
path passed via ``CCPPFrameworkEnv.ccpp_datafile``).  The compat layer
renames the produced file to bridge that naming gap; if no rename is
needed it is a no-op.
"""

import logging
import os
import tempfile
import unittest

from _runner import _rename_datatable


class TestRenameDatatable(unittest.TestCase):

    def _produce(self, output_root):
        path = os.path.join(output_root, 'datatable.xml')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('<ccpp_datatable version="1.0"/>\n')
        return path

    def test_rename_to_ccpp_prefix_same_dir(self):
        # The canonical CAM-SIMA case: same directory, basename
        # changes from ``datatable.xml`` -> ``ccpp_datatable.xml``.
        with tempfile.TemporaryDirectory() as out:
            self._produce(out)
            target = os.path.join(out, 'ccpp_datatable.xml')
            _rename_datatable(out, target, logging.getLogger('test'))
            self.assertTrue(os.path.isfile(target))
            self.assertFalse(os.path.isfile(os.path.join(out, 'datatable.xml')))

    def test_noop_when_already_matches(self):
        # Requested path is exactly what capgen produced; the
        # rename is a no-op and must not delete the file.
        with tempfile.TemporaryDirectory() as out:
            produced = self._produce(out)
            _rename_datatable(out, produced, logging.getLogger('test'))
            self.assertTrue(os.path.isfile(produced))

    def test_rename_across_directories(self):
        # Some CAM-SIMA build configurations point ccpp_datafile at a
        # sibling directory; the helper must create the target dir.
        with tempfile.TemporaryDirectory() as out:
            self._produce(out)
            target = os.path.join(out, 'sub', 'renamed.xml')
            _rename_datatable(out, target, logging.getLogger('test'))
            self.assertTrue(os.path.isfile(target))

    def test_missing_source_logs_warning(self):
        # If capgen didn't produce the file for some reason,
        # the helper warns rather than raising -- the caller has
        # better context for failure handling.
        with tempfile.TemporaryDirectory() as out:
            target = os.path.join(out, 'ccpp_datatable.xml')
            with self.assertLogs(level='WARNING') as cm:
                _rename_datatable(out, target, logging.getLogger('test'))
            self.assertTrue(any('did not write' in m for m in cm.output))


if __name__ == '__main__':
    unittest.main()

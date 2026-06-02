#! /usr/bin/env python3
"""Run the CAM-SIMA capgen_compat unit tests.

Usage::

    cd test/unit/python/capgen_compat
    python run_compat_tests.py

Discovers every ``compat_test_*.py`` in this directory.  Kept separate
from CAM-SIMA's main test runner so the compat-layer tests can run in
isolation in CI.
"""

import os
import sys
import unittest


_HERE      = os.path.dirname(os.path.abspath(__file__))
_CAM_ROOT  = os.path.abspath(os.path.join(_HERE, os.pardir,
                                          os.pardir, os.pardir, os.pardir))
_COMPAT    = os.path.join(_CAM_ROOT, "cime_config", "capgen_compat")
_CAPGEN_NG = os.path.join(_CAM_ROOT, "ccpp_framework", "capgen-ng")

# Same sys.path order test_write_init_files.py uses: compat shims
# (and their internal sibling modules) on the front; capgen-ng itself
# appended.  All compat modules live as flat top-level imports.
sys.path.insert(0, _COMPAT)
if _CAPGEN_NG not in sys.path:
    sys.path.append(_CAPGEN_NG)


def main(argv=None):
    loader = unittest.TestLoader()
    suite  = loader.discover(start_dir=_HERE, pattern='compat_test_*.py')
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())

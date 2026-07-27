"""
Python unit testing collection for host_framework_deps.py, which declares
the CCPP framework Fortran sources that CAM-SIMA's host code compiles in
every configuration (independent of the suites being built).

To run these unit tests, simply type:

python test_host_framework_deps.py

or (for more verbose output):

python test_host_framework_deps.py -v
"""

#----------------------------------------
#Import required python libraries/modules:
#----------------------------------------
import os
import os.path
import re
import sys
import tempfile
import shutil

#Python unit-testing library:
import unittest

#Add directory to python path:
_CURRDIR = os.path.abspath(os.path.dirname(__file__))
_CAM_ROOT_DIR = os.path.join(_CURRDIR, os.pardir, os.pardir, os.pardir)
_CAM_CONF_DIR = os.path.abspath(os.path.join(_CAM_ROOT_DIR, "cime_config"))

#Check for all necessary directories:
if not os.path.exists(_CAM_CONF_DIR):
    _EMSG = f"ERROR: Cannot find required '{_CAM_CONF_DIR}' directory"
    raise ImportError(_EMSG)
#End if

#Add "cime_config" directory to python path:
sys.path.append(_CAM_CONF_DIR)

# pylint: disable=wrong-import-position
from host_framework_deps import host_framework_sources
from host_framework_deps import HostFrameworkDepsError
from host_framework_deps import CAPGEN_SRC_DIR
# pylint: enable=wrong-import-position

# Fortran modules that CAM-SIMA host code obtains from somewhere other than
# capgen/src, so a `use` of them is not evidence of a missing source file.
# ccpp_kinds.F90 is generated per-build by capgen and arrives via
# datatable.xml's <utilities>.
_GENERATED_MODULES = {"ccpp_kinds"}

_USE_RE = re.compile(r"^\s*use\s+(ccpp_\w+)", re.IGNORECASE | re.MULTILINE)


class HostFrameworkDepsTest(unittest.TestCase):

    """Tests for host_framework_sources"""

    def test_paths_are_absolute_and_exist(self):
        """Every returned path must be absolute and resolve to a real file."""
        for path in host_framework_sources():
            self.assertTrue(os.path.isabs(path), msg=f"not absolute: {path}")
            self.assertTrue(os.path.isfile(path), msg=f"missing: {path}")
        #End for

    def test_sorted_for_reproducible_ordering(self):
        """The list must be sorted so build inputs do not vary run to run."""
        sources = host_framework_sources()
        self.assertEqual(sources, sorted(sources))

    def test_includes_constituent_prop_mod(self):
        """
        ccpp_constituent_prop_mod is the load-bearing entry: CAM-SIMA's
        cam_comp.F90, cam_constituents.F90 and ccpp_const_utils.F90 all USE
        it, and all three are compiled for every suite.  Omitting it makes a
        constituent-free suite fail with "Cannot open module file
        'ccpp_constituent_prop_mod.mod'".
        """
        names = [os.path.basename(p) for p in host_framework_sources()]
        self.assertIn("ccpp_constituent_prop_mod.F90", names)

    def test_module_use_closure(self):
        """
        The returned set must be closed under `use`: a module used by one of
        these files must either be in the set itself or be generated
        per-build.  Guards against a partial list, which would fail at link
        or compile time rather than here.
        """
        sources = host_framework_sources()
        provided = {
            os.path.splitext(os.path.basename(p))[0].lower() for p in sources
        }
        for path in sources:
            with open(path, "r", encoding="utf-8") as sfile:
                used = {m.lower() for m in _USE_RE.findall(sfile.read())}
            #End with
            unresolved = used - provided - _GENERATED_MODULES
            self.assertEqual(unresolved, set(),
                             msg=f"{os.path.basename(path)} uses modules that "
                                 f"host_framework_sources does not provide: "
                                 f"{sorted(unresolved)}")
        #End for

    def test_default_dir_matches_capgen_src(self):
        """The default search directory is capgen's own src directory."""
        self.assertTrue(os.path.isdir(CAPGEN_SRC_DIR))
        for path in host_framework_sources():
            self.assertEqual(os.path.dirname(path),
                             os.path.abspath(CAPGEN_SRC_DIR))
        #End for

    def test_missing_directory_raises(self):
        """A missing source directory is an error, with a fleximod hint."""
        bad_dir = os.path.join(_CURRDIR, "definitely_not_a_directory")
        with self.assertRaises(HostFrameworkDepsError) as cerr:
            host_framework_sources(capgen_src_dir=bad_dir)
        #End with
        emsg = str(cerr.exception)
        self.assertIn(bad_dir, emsg)
        self.assertIn("git-fleximod", emsg)

    def test_empty_directory_raises(self):
        """
        An existing but empty directory is also an error -- it means a
        broken checkout, and silently returning [] would defer the failure
        to an opaque "Cannot open module file" at compile time.
        """
        tmpdir = tempfile.mkdtemp()
        try:
            with self.assertRaises(HostFrameworkDepsError) as cerr:
                host_framework_sources(capgen_src_dir=tmpdir)
            #End with
            emsg = str(cerr.exception)
            self.assertIn("ccpp_constituent_prop_mod", emsg)
            self.assertIn("git-fleximod", emsg)
        finally:
            shutil.rmtree(tmpdir)
        #End try

    def test_explicit_dir_is_honored(self):
        """An explicit directory overrides the default."""
        tmpdir = tempfile.mkdtemp()
        try:
            stub = os.path.join(tmpdir, "ccpp_stub_mod.F90")
            with open(stub, "w", encoding="utf-8") as sfile:
                sfile.write("module ccpp_stub_mod\nend module ccpp_stub_mod\n")
            #End with
            sources = host_framework_sources(capgen_src_dir=tmpdir)
            self.assertEqual([os.path.basename(p) for p in sources],
                             ["ccpp_stub_mod.F90"])
        finally:
            shutil.rmtree(tmpdir)
        #End try


#################################################
#Run unit tests if this script is called directly
#################################################

if __name__ == "__main__":
    unittest.main()

############
#End of file
############

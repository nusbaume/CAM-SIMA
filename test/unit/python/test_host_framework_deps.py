"""
Python unit testing collection for host_framework_deps.py, which declares
the CCPP framework Fortran modules that CAM-SIMA's host code compiles
against in every configuration (independent of the suites being built).

To run these unit tests, simply type:

python test_host_framework_deps.py

or (for more verbose output):

python test_host_framework_deps.py -v
"""

#----------------------------------------
#Import required python libraries/modules:
#----------------------------------------
import glob
import os
import os.path
import re
import sys

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
from host_framework_deps import check_host_framework_deps
from host_framework_deps import HostFrameworkDepsError
from host_framework_deps import HOST_REQUIRED_FRAMEWORK_MODULES
from host_framework_deps import CAPGEN_SRC_DIR
# pylint: enable=wrong-import-position

# Fortran modules obtained from somewhere other than capgen/src, so a `use`
# of them is not evidence of a missing source file.  ccpp_kinds.F90 is
# generated per-build by capgen and arrives via datatable.xml's <utilities>.
_GENERATED_MODULES = {"ccpp_kinds"}

_USE_RE = re.compile(r"^\s*use\s+(ccpp_\w+)", re.IGNORECASE | re.MULTILINE)

# A plausible <utilities> list for a build whose suite has no constituents.
# Since ccpp-framework e1f90d1 capgen emits all of these unconditionally.
_UTILITIES_SAMPLE = [
    "/build/ccpp/ccpp_kinds.F90",
    "/build/ccpp/ccpp_host_constituents.F90",
    "/fw/capgen/src/ccpp_constituent_prop_mod.F90",
    "/fw/capgen/src/ccpp_hashable.F90",
    "/fw/capgen/src/ccpp_hash_table.F90",
    "/fw/capgen/src/ccpp_scheme_utils.F90",
]


class HostFrameworkDepsTest(unittest.TestCase):

    """Tests for check_host_framework_deps"""

    def test_complete_utilities_list_passes(self):
        """A <utilities> list with every required module is accepted."""
        self.assertEqual(check_host_framework_deps(_UTILITIES_SAMPLE),
                         sorted(HOST_REQUIRED_FRAMEWORK_MODULES))

    def test_extra_files_are_ignored(self):
        """Modules CAM-SIMA does not require are not the check's business."""
        check_host_framework_deps(_UTILITIES_SAMPLE + ["/fw/ccpp_future.F90"])

    def test_empty_entries_tolerated(self):
        """
        cam_autogen builds the list with ''.split(';'), which yields [''] for
        an empty report -- an empty string must not be read as a module name.
        """
        with self.assertRaises(HostFrameworkDepsError):
            check_host_framework_deps([""])
        #End with

    def test_missing_constituent_prop_mod_raises(self):
        """
        ccpp_constituent_prop_mod is the load-bearing entry: cam_comp.F90,
        cam_constituents.F90 and ccpp_const_utils.F90 all USE it, and all
        three are compiled for every suite.  Its absence must be reported
        here rather than as "Cannot open module file" at compile time.
        """
        utils = [p for p in _UTILITIES_SAMPLE if "constituent_prop" not in p]
        with self.assertRaises(HostFrameworkDepsError) as cerr:
            check_host_framework_deps(utils)
        #End with
        self.assertIn("ccpp_constituent_prop_mod", str(cerr.exception))

    def test_missing_scheme_utils_raises(self):
        """ccpp_scheme_utils: used by the NUOPC cap, atm_import_export.F90."""
        utils = [p for p in _UTILITIES_SAMPLE if "scheme_utils" not in p]
        with self.assertRaises(HostFrameworkDepsError) as cerr:
            check_host_framework_deps(utils)
        #End with
        self.assertIn("ccpp_scheme_utils", str(cerr.exception))

    def test_error_names_the_cam_sima_consumers(self):
        """
        The message must name the CAM-SIMA files that force the dependency:
        whoever hits this needs to know whether to fix the framework version
        or delete a use statement, and cannot tell without them.
        """
        emsg = ""
        try:
            check_host_framework_deps(["/build/ccpp/ccpp_kinds.F90"])
        except HostFrameworkDepsError as derr:
            emsg = str(derr)
        #End try
        self.assertIn("src/control/cam_comp.F90", emsg)
        self.assertIn("src/cpl/nuopc/atm_import_export.F90", emsg)
        # ...and what it did get, so the gap is visible without a rerun.
        self.assertIn("ccpp_kinds", emsg)

    def test_required_modules_exist_in_framework(self):
        """
        Every required module must be a real file in the checked-out
        framework.  Guards against a typo in the table, which would
        otherwise fail every build with a misleading message.
        """
        self.assertTrue(os.path.isdir(CAPGEN_SRC_DIR),
                        msg=f"missing: {CAPGEN_SRC_DIR}. Run 'git-fleximod'?")
        available = {
            os.path.splitext(os.path.basename(p))[0].lower()
            for p in glob.glob(os.path.join(CAPGEN_SRC_DIR, "*.F90"))
        }
        for module in HOST_REQUIRED_FRAMEWORK_MODULES:
            self.assertIn(module, available)
        #End for

    def test_consumers_still_use_the_module(self):
        """
        Each table entry must still be justified by a real use statement in
        CAM-SIMA.  Keeps the table shrinking as the migration proceeds
        instead of accumulating dependencies nobody has anymore.  Wildcard
        entries are skipped -- they are documentation for the reader.
        """
        for module, users in HOST_REQUIRED_FRAMEWORK_MODULES.items():
            use_re = re.compile(rf"^\s*use\s+{module}\b",
                                re.IGNORECASE | re.MULTILINE)
            for user in users:
                if any(char in user for char in "*{"):
                    continue
                #End if
                path = os.path.join(_CAM_ROOT_DIR, user)
                self.assertTrue(os.path.isfile(path), msg=f"missing: {user}")
                with open(path, "r", encoding="utf-8") as sfile:
                    self.assertRegex(sfile.read(), use_re,
                                     msg=f"{user} no longer uses {module}")
                #End with
            #End for
        #End for

    def test_framework_module_use_closure(self):
        """
        The framework sources must be closed under `use`: a module used by
        one of them must either live in capgen/src too or be generated
        per-build.  The build-time check deliberately does not test this, so
        it is tested here -- a gap would surface at compile or link time.
        """
        sources = glob.glob(os.path.join(CAPGEN_SRC_DIR, "*.F90"))
        self.assertTrue(sources, msg=f"no sources in {CAPGEN_SRC_DIR}")
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
                                 f"capgen/src does not provide: "
                                 f"{sorted(unresolved)}")
        #End for


#################################################
#Run unit tests if this script is called directly
#################################################

if __name__ == "__main__":
    unittest.main()

############
#End of file
############

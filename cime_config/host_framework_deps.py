"""
Framework Fortran sources that CAM-SIMA's *host* code needs in every build.

Why this exists
---------------
capgen lists the Fortran sources it thinks a build needs in
``datatable.xml``'s ``<utilities>`` section, and ``cam_autogen.py`` copies
those into the generated-code directory.  capgen derives that list from the
*suites* being built: it emits ``ccpp_constituent_prop_mod.F90`` and its
dependencies only when some suite touches constituent state.  That is the
right call for capgen -- it can only see metadata, so it can only speak to
what the generated caps require.

CAM-SIMA's own host code, however, ``use``s ``ccpp_constituent_prop_mod``
unconditionally, in files that are compiled for every configuration:

    src/control/cam_comp.F90                       (top-level driver)
    src/physics/utils/cam_constituents.F90         (src/physics/utils is
                                                    unconditional in Filepath)
    src/physics/ncar_ccpp/to_be_ccppized/ccpp_const_utils.F90
                                                   (all of to_be_ccppized/ is
                                                    copied unconditionally)
    src/dynamics/{mpas,se}/...                     (dycore coupling)
    src/dynamics/tests/initial_conditions/*.F90    (analytic ICs)

So for CAM-SIMA the module is always required, whether or not the configured
suite mentions a constituent.  Building a constituent-free suite -- e.g.
``suite_beljaars_form_drag.xml``, whose two schemes contain zero constituent
metadata -- otherwise fails at compile time with::

    ccpp_const_utils.F90:13:9:
       use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
    Fatal Error: Cannot open module file 'ccpp_constituent_prop_mod.mod'

Original capgen papered over this by listing the framework sources in
``<utilities>`` on every run (``scripts/ccpp_datafile.py``,
``_add_generated_files``).  That made the framework assert a dependency it
could not see, on behalf of every host.  Declaring it here instead keeps
that knowledge with the code that actually has it.

Scope
-----
This module holds **only** framework sources that CAM-SIMA compiles
unconditionally.  It is not a general dumping ground for build fixes, and it
is deliberately *not* part of ``cime_config/capgen_compat/``: that directory
is transient scaffolding for the original-capgen -> capgen migration and is
scheduled for deletion, whereas this dependency outlives it.  CAM-SIMA host
code will keep using ``ccpp_constituent_prop_mod`` no matter which generator
produces the caps.

This module can be deleted when no CAM-SIMA source compiled unconditionally
``use``s a framework module -- i.e. when the constituent API is reached only
through generated caps.  Until then, shrinking the list above is what makes
this file smaller.
"""

import os
import glob

_CIME_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CAM_ROOT_DIR = os.path.dirname(_CIME_CONFIG_DIR)

# capgen ships its runtime Fortran modules in capgen/src.  Same directory
# cam_autogen.py resolves for the capgen Python entry points.
CAPGEN_SRC_DIR = os.path.join(_CAM_ROOT_DIR, "ccpp_framework", "capgen", "src")


class HostFrameworkDepsError(ValueError):
    """Raised when the framework sources cannot be located."""


###############################################################################
def host_framework_sources(capgen_src_dir=None):
###############################################################################
    """
    Return absolute paths of the framework Fortran sources that CAM-SIMA's
    host code requires in every build, sorted for reproducible ordering.

    The whole of capgen's ``src`` directory is taken rather than a hard-coded
    file list: the modules there form one dependency cluster
    (``ccpp_constituent_prop_mod`` uses ``ccpp_hashable`` and
    ``ccpp_hash_table``; constituent index lookups use ``ccpp_scheme_utils``),
    and globbing means a framework-side addition does not silently break the
    CAM-SIMA build.

    Files are copied into the generated-code directory by the caller, which
    is also where capgen's own ``<utilities>`` files land -- so when a suite
    *does* use constituents and capgen lists these too, both writes target
    the same path with identical content and no duplicate module results.

    >>> paths = host_framework_sources()
    >>> [os.path.basename(p) for p in paths]  # doctest: +ELLIPSIS
    [...'ccpp_constituent_prop_mod.F90'...]
    """
    src_dir = capgen_src_dir if capgen_src_dir else CAPGEN_SRC_DIR

    if not os.path.isdir(src_dir):
        emsg = "ERROR: Unable to find CCPP framework source directory:\n"
        emsg += f" {src_dir}\n Have you run 'git-fleximod'?"
        raise HostFrameworkDepsError(emsg)
    # end if

    sources = sorted(glob.glob(os.path.join(src_dir, "*.F90")))

    if not sources:
        emsg = "ERROR: No Fortran sources found in CCPP framework source\n"
        emsg += f" directory: {src_dir}\n"
        emsg += " CAM-SIMA host code requires ccpp_constituent_prop_mod.\n"
        emsg += " Have you run 'git-fleximod'?"
        raise HostFrameworkDepsError(emsg)
    # end if

    return [os.path.abspath(path) for path in sources]

###############################################################################

if __name__ == "__main__":
    import doctest
    doctest.testmod()

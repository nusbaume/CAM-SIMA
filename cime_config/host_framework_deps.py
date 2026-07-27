"""
Framework Fortran modules that CAM-SIMA's *host* code needs in every build.

Why this exists
---------------
capgen lists the Fortran sources a build needs in ``datatable.xml``'s
``<utilities>`` section, and ``cam_autogen.py`` copies those into the
generated-code directory.  That list is derived from what the generated caps
require -- capgen sees suite and scheme metadata, so that is the only thing
it can speak to.

CAM-SIMA's own host code also ``use``s framework modules directly, in files
that are compiled for every configuration regardless of the suite:

    ccpp_constituent_prop_mod
        src/control/cam_comp.F90                    (top-level driver)
        src/physics/utils/cam_constituents.F90      (src/physics/utils is
                                                     unconditional in Filepath)
        src/physics/utils/physics_data.F90
        src/physics/ncar_ccpp/to_be_ccppized/ccpp_const_utils.F90
                                                    (all of to_be_ccppized/ is
                                                     copied unconditionally)
        src/dynamics/{mpas,se}/...                  (dycore coupling)
        src/dynamics/tests/initial_conditions/*.F90 (analytic ICs)

    ccpp_scheme_utils
        src/cpl/nuopc/atm_import_export.F90         (NUOPC cap)

Nothing in the framework can see those ``use`` statements, so nothing in the
framework can promise to keep shipping the modules behind them.  As of
ccpp-framework e1f90d1 the promise happens to hold: ``ccpp_host_constituents``
is generated unconditionally (the host cap re-exports its API, so that
interface must not vary with suite content), which drags
``ccpp_constituent_prop_mod`` and its dependency cluster into ``<utilities>``
on every run.  CAM-SIMA is a beneficiary of that decision, not a party to it.

So this module does not *supply* anything -- it *checks*.  Supplying was the
earlier approach and it was wrong in a specific way: copying capgen/src into
the build directory unconditionally would silently paper over a framework
that had stopped shipping what CAM-SIMA needs, which is exactly the case
worth hearing about, and it left two lists (a glob here, an explicit list in
``ccpp_capgen.py``) free to drift apart.  Checking keeps the knowledge on the
CAM-SIMA side, where the ``use`` statements are, without duplicating the
delivery mechanism.

The failure this prevents is a compile-time error a long way from its cause::

    ccpp_const_utils.F90:13:9:
       use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
    Fatal Error: Cannot open module file 'ccpp_constituent_prop_mod.mod'

Scope
-----
This module holds **only** framework modules that CAM-SIMA compiles
unconditionally.  It is not a general dumping ground for build fixes, and it
is deliberately *not* part of ``cime_config/capgen_compat/``: that directory
is transient scaffolding for the original-capgen -> capgen migration and is
scheduled for deletion, whereas this dependency outlives it.  CAM-SIMA host
code will keep using ``ccpp_constituent_prop_mod`` no matter which generator
produces the caps.

Schemes are out of scope: they are compiled only when their suite is built,
so capgen's own dependency tracking already covers them.  Files under
``src/physics/ncar_ccpp/test/`` are likewise out of scope.

This module can be deleted when no CAM-SIMA source compiled unconditionally
``use``s a framework module -- i.e. when the framework API is reached only
through generated caps.  Until then, shrinking the table below is what makes
this file smaller.
"""

import os

_CIME_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CAM_ROOT_DIR = os.path.dirname(_CIME_CONFIG_DIR)

# capgen ships its runtime Fortran modules in capgen/src.  Same directory
# cam_autogen.py resolves for the capgen Python entry points.  Used by the
# unit tests to check this file against the framework actually checked out.
CAPGEN_SRC_DIR = os.path.join(_CAM_ROOT_DIR, "ccpp_framework", "capgen", "src")

# Framework module -> the CAM-SIMA files that USE it, for the error message.
# Every entry must be a file compiled in *every* configuration; see the
# module docstring for why schemes do not belong here.
HOST_REQUIRED_FRAMEWORK_MODULES = {
    "ccpp_constituent_prop_mod": (
        "src/control/cam_comp.F90",
        "src/physics/utils/cam_constituents.F90",
        "src/physics/utils/physics_data.F90",
        "src/physics/ncar_ccpp/to_be_ccppized/ccpp_const_utils.F90",
        "src/dynamics/{mpas,se}/... (dycore coupling)",
        "src/dynamics/tests/initial_conditions/*.F90",
    ),
    "ccpp_scheme_utils": (
        "src/cpl/nuopc/atm_import_export.F90",
    ),
}


class HostFrameworkDepsError(ValueError):
    """Raised when capgen's utility files omit a module host code requires."""


###############################################################################
def check_host_framework_deps(utility_files):
###############################################################################
    """
    Verify that <utility_files> -- capgen's ``<utilities>`` list for this
    build -- provides every framework module CAM-SIMA host code compiles
    against unconditionally.  Return the sorted list of required module
    names on success; raise HostFrameworkDepsError naming the affected
    CAM-SIMA files otherwise.

    Only the modules in HOST_REQUIRED_FRAMEWORK_MODULES are checked, not
    their dependency closure: a module that is present but unbuildable is a
    broken framework checkout rather than a CAM-SIMA/framework interface
    problem, and the unit tests cover closure against capgen/src directly.

    >>> check_host_framework_deps(["/x/ccpp_constituent_prop_mod.F90",
    ...                            "/x/ccpp_scheme_utils.F90"])
    ['ccpp_constituent_prop_mod', 'ccpp_scheme_utils']
    """
    provided = {
        os.path.splitext(os.path.basename(path))[0].lower()
        for path in utility_files if path
    }
    missing = sorted(set(HOST_REQUIRED_FRAMEWORK_MODULES) - provided)

    if missing:
        emsg = "ERROR: The CCPP framework did not provide Fortran module(s)\n"
        emsg += " that CAM-SIMA host code compiles against in every build:\n"
        for module in missing:
            emsg += f"\n {module}, used by:\n"
            for user in HOST_REQUIRED_FRAMEWORK_MODULES[module]:
                emsg += f"   {user}\n"
            # end for
        # end for
        emsg += "\n capgen lists the sources a build needs in datatable.xml's\n"
        emsg += " <utilities> section; the module(s) above were not in it.\n"
        emsg += " This usually means the ccpp_framework submodule no longer\n"
        emsg += " emits them unconditionally.  Check the framework version,\n"
        emsg += " or drop the CAM-SIMA use statements listed above.\n"
        emsg += " Modules provided by this build:\n"
        emsg += f"   {', '.join(sorted(provided)) if provided else '(none)'}\n"
        raise HostFrameworkDepsError(emsg)
    # end if

    return sorted(HOST_REQUIRED_FRAMEWORK_MODULES)

###############################################################################

if __name__ == "__main__":
    import doctest
    doctest.testmod()

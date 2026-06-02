"""Flat-module shim: re-exports ``capgen`` and ``CapDatabase``.

Lets CAM-SIMA's existing ``from ccpp_capgen import capgen`` style work
once ``cime_config/capgen_compat/`` is on ``sys.path``.
"""

# Import from the sibling internal modules directly so this file works
# whether ``capgen_compat`` is reached as a package (cime_config/ on
# sys.path) or via the flat-module layout (only the directory itself
# on sys.path).  CAM-SIMA's cam_autogen.py uses the latter.
from _runner       import capgen        # noqa: F401
from _cap_database import CapDatabase   # noqa: F401

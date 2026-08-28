"""Flat-module shim for original capgen's ``ddt_library``.

``src/data/write_init_files.py`` does ``from ddt_library import VarDDT``
and uses the class only in an ``isinstance`` test, to tell a variable
reached by walking into a DDT (a component, handled by the normal
read/check path) apart from a whole-DDT host variable (which cannot be
read from an initial-conditions file).

Capgen has no ``ddt_library``: it carries the DDT walk on
``HostVarEntry.access_path`` instead of in the variable's class.  The
CapDatabase adapter reconstructs the class distinction -- see
``_var_wrapper._VarDDT`` and ``_VarWrapper.from_host_entry`` -- and this
module re-exports it under the name CAM-SIMA imports.

Retires with the rest of the CapDatabase adapter (README phase B).
"""

from _var_wrapper import _VarDDT as VarDDT

__all__ = ['VarDDT']

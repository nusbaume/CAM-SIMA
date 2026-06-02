"""Flat-module shim for original capgen's ``fortran_tools`` package.

Re-exports ``FortranWriter`` from the vendored :mod:`fortran_write`
module.  Original capgen ships ``fortran_tools`` as a package with
``__init__.py`` re-exporting from ``fortran_write.py``; CAM-SIMA's
``write_init_files.py`` and ``generate_registry_data.py`` import
``FortranWriter`` directly.

The vendored ``fortran_write.py`` is a verbatim copy of the
``fortran_write.py`` shipped in the original CAM-SIMA ccpp_framework
checkout.  Update it (and bump the comment below) if a newer release
introduces fixes we need.
"""

from fortran_write import FortranWriter  # noqa: F401

__all__ = ['FortranWriter']

"""``capgen(run_env, return_db=True)`` entry point.

Translates a :class:`CCPPFrameworkEnv` into capgen-ng's keyword API,
runs the generator with ``return_state=True``, and wraps the resolved
state in a :class:`CapDatabase` facade.

Capgen-ng options with no equivalent in :class:`CCPPFrameworkEnv` are
ignored with a debug log:

* ``generate_docfiles`` -- capgen-ng emits an inspection ``.meta`` for
  each suite plus the introspection routines unconditionally; no
  on/off toggle.
* ``use_error_obj`` -- capgen-ng always raises ``CCPPError``.

``force_overwrite`` is silently honoured because every generated file
routes through ``write_if_changed`` (so re-running is always cheap).
"""

import logging
from typing import Dict, Tuple

from _cap_database import CapDatabase


# Map CCPPFrameworkEnv attribute → capgen-ng keyword name.
_KWARG_MAP = {
    'host_files':   'host_files',
    'scheme_files': 'scheme_files',
    'suites':       'suite_files',
    'host_name':    'host_name',
    'output_root':  'output_root',
    'kind_types':   'kind_types',
}


def _translate_kind_types(value) -> Dict[str, Tuple[str, str]]:
    """Normalise *value* to capgen-ng's ``{name: (module, spec)}`` form.

    Three input shapes are accepted, in priority order:

    1. ``list of str`` -- the CLI-style format CAM-SIMA passes today
       (``['kind_phys=REAL64', 'kind_dyn=my_mod:kind_r4']``).
       Delegated to capgen-ng's own ``_parse_kind_types`` so the
       grammar stays consistent with ``--kind-type``.
    2. ``{name: (module, spec)}`` -- the full dict form; passed
       through unchanged.
    3. ``{name: spec}`` -- the legacy short dict form; default the
       module to ``iso_fortran_env``.
    """
    if value is None:
        return {}
    if isinstance(value, list):
        # CLI-string list -- delegate to capgen-ng's canonical parser.
        from ccpp_capgen_ng import _parse_kind_types
        return _parse_kind_types(value)
    out: Dict[str, Tuple[str, str]] = {}
    for name, raw in value.items():
        if isinstance(raw, tuple) and len(raw) == 2:
            out[name] = (str(raw[0]), str(raw[1]))
        else:
            out[name] = ('iso_fortran_env', str(raw))
    return out


def capgen(run_env, return_db: bool = False):
    """Original-capgen-shaped capgen entry.

    Parameters
    ----------
    run_env : CCPPFrameworkEnv
    return_db : bool, optional
        When ``True``, return a :class:`CapDatabase` after generating
        the caps; when ``False`` (the original-capgen default), run
        the generation side-effects only and return ``None``.

    Returns
    -------
    CapDatabase or None

    Raises
    ------
    CCPPError
        On any capgen-ng error.
    """
    from ccpp_capgen_ng import capgen as _capgen_ng

    logger = getattr(run_env, 'logger', None) or logging.getLogger(__name__)

    cn_kwargs = {}
    for env_attr, cn_kwarg in _KWARG_MAP.items():
        value = getattr(run_env, env_attr, None)
        if value is None:
            continue
        if env_attr == 'kind_types':
            value = _translate_kind_types(value)
        elif env_attr in ('host_files', 'scheme_files', 'suites'):
            # CAM-SIMA's test fixtures pass either a single path
            # string (``scheme_files = ".../temp_adjust.meta"``) or a
            # list of paths.  capgen-ng's keyword API expects a list;
            # normalise.  An empty string maps to an empty list so
            # capgen-ng's "no scheme files" path triggers cleanly.
            if isinstance(value, str):
                value = [value] if value else []
        cn_kwargs[cn_kwarg] = value

    for required in ('host_name', 'output_root',
                     'host_files', 'scheme_files', 'suite_files'):
        if required not in cn_kwargs:
            raise ValueError(
                "capgen_compat.capgen: CCPPFrameworkEnv did not supply "
                "required attribute mapping to capgen-ng kwarg '{}'; "
                "check that run_env was constructed with the matching "
                "kwarg before the capgen() call.".format(required)
            )

    cn_kwargs.setdefault('kind_types', {})

    for ignored in ('generate_docfiles', 'use_error_obj',
                    'force_overwrite', 'preproc_directives',
                    'ccpp_datafile'):
        value = getattr(run_env, ignored, None)
        if value is not None:
            logger.debug(
                "capgen_compat: ignoring CCPPFrameworkEnv option "
                "%r=%r (no capgen-ng equivalent)",
                ignored, value,
            )

    cn_kwargs['return_state'] = True
    cn_kwargs['logger'] = logger

    # Pre-scan every host/scheme .meta file for the
    # ``# capgen_compat:original_type = module`` marker so
    # ``MODULE_ORIGIN_TABLE_NAMES`` is populated before
    # capgen-ng's internal parse runs.  ``_VarWrapper.from_host_entry``
    # consults that set to decide ``source.ptype``.  Without the
    # pre-scan, registry-generated module vars get tagged
    # ``ptype = 'host'`` and write_init_files's
    # ``ptype != 'host'`` filter excludes them, producing an empty
    # ``phys_var_stdnames`` list.
    from metadata_table import _scan_module_origin_tables, MODULE_ORIGIN_TABLE_NAMES
    for path in (cn_kwargs.get('host_files', []) or []) + \
                (cn_kwargs.get('scheme_files', []) or []):
        MODULE_ORIGIN_TABLE_NAMES.update(_scan_module_origin_tables(path))

    # Transient migration shims.  Capgen-ng's CLI enables these by
    # calling a module-level ``enable()`` *before* the ``capgen()``
    # function runs; do the same here when the matching kwarg is
    # truthy on the CCPPFrameworkEnv.  Each enable() emits a loud
    # startup banner.
    if getattr(run_env, 'legacy_mode', False):
        from metadata import legacy_compat
        legacy_compat.enable(logger)
    if getattr(run_env, 'gfs_dim_aliases', False):
        from metadata import dim_aliases
        dim_aliases.enable(logger)
    if getattr(run_env, 'legacy_auto_clone_constituents', False):
        from metadata import auto_clone_constituents
        auto_clone_constituents.enable(logger)

    host_dict, suite_resolutions = _capgen_ng(**cn_kwargs)

    if not return_db:
        return None
    return CapDatabase(host_dict, suite_resolutions)

"""Minimal stub for ``ccpp_framework.framework_env.CCPPFrameworkEnv``.

Receives the positional logger + kwargs that ``cam_autogen.py:647``
passes, exposes them as attributes for :func:`_runner.capgen` to map
to capgen's keyword API.
"""

_KNOWN_KWARGS = frozenset({
    'host_files', 'scheme_files', 'suites',
    'preproc_directives', 'generate_docfiles',
    'host_name', 'kind_types',
    'use_error_obj', 'force_overwrite',
    'output_root', 'ccpp_datafile',
    # capgen-specific transient migration shims.  Set to True to
    # opt into the matching shim while CAM-SIMA metadata is being
    # migrated off the deprecated spellings.
    'legacy_mode',          # horizontal_loop_extent + number_of_openmp_threads
    'gfs_dim_aliases',      # GFS radiation/composition vertical dim aliases
    'legacy_auto_clone_constituents',  # original-capgen auto-clone path
})


# Per-kwarg default values.  Any name not listed here defaults to
# ``None`` -- the inherited "absent" sentinel original capgen's class
# also uses.
#
# ``legacy_mode`` defaults to ``True`` because the bulk of CAM-SIMA's
# scheme metadata still spells the horizontal axis as
# ``horizontal_loop_extent`` (119 .meta files at last count) and the
# OpenMP thread count as ``number_of_openmp_threads``; the shim is
# silent on metadata that already uses the canonical capgen names,
# so leaving it on costs nothing for migrated metadata.  Explicitly
# pass ``legacy_mode=False`` to disable.
#
# ``legacy_auto_clone_constituents`` defaults to ``True`` because
# CAM-SIMA's atmospheric_physics tree relies on original capgen's
# auto-clone-static-constituent path: ~16 schemes (kessler, zm_convr,
# dadadj, holtslag_boville_diff, state_converters, geopotential_temp,
# cloud_particle_sedimentation, …) declare ``advected = True`` on
# their ``_run`` arg-tables and let the framework register the
# constituent on their behalf.  Without the shim, capgen's stricter
# rule -- physics phases may only produce tendencies, not new base
# constituents -- fires on the first such scheme.  The shim is
# single-instance only; capgen aborts before parsing if the host
# declares ``instance_number`` + ``number_of_instances``, so leaving
# it on is safe for any single-instance CAM-SIMA build.  Explicitly
# pass ``legacy_auto_clone_constituents=False`` to disable.
_KWARG_DEFAULTS = {
    'legacy_mode': True,
    'legacy_auto_clone_constituents': True,
}


class CCPPFrameworkEnv:
    """Opaque-ish config object.

    Stores constructor arguments verbatim on the instance.  Unknown
    kwargs are accepted silently so a future cam-sima signature
    extension doesn't break compat.
    """

    def __init__(self, logger, **kwargs):
        self.logger = logger

        # Pre-populate every known kwarg with its declared default
        # (``None`` for everything not listed in ``_KWARG_DEFAULTS``)
        # so attribute access never raises AttributeError even if the
        # caller omits an optional kwarg.
        for name in _KNOWN_KWARGS:
            setattr(self, name, _KWARG_DEFAULTS.get(name, None))

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __repr__(self) -> str:
        populated = sum(1 for name in _KNOWN_KWARGS
                        if getattr(self, name, None) is not None)
        return ('CCPPFrameworkEnv(host_name={!r}, populated_kwargs={}, '
                'logger={!r})'.format(
                    self.host_name, populated, self.logger,
                ))

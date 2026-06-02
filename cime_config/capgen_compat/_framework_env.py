"""Minimal stub for ``ccpp_framework.framework_env.CCPPFrameworkEnv``.

Receives the positional logger + kwargs that ``cam_autogen.py:647``
passes, exposes them as attributes for :func:`_runner.capgen` to map
to capgen-ng's keyword API.
"""

_KNOWN_KWARGS = frozenset({
    'host_files', 'scheme_files', 'suites',
    'preproc_directives', 'generate_docfiles',
    'host_name', 'kind_types',
    'use_error_obj', 'force_overwrite',
    'output_root', 'ccpp_datafile',
    # capgen-ng-specific transient migration shims.  Set to True to
    # opt into the matching shim while CAM-SIMA metadata is being
    # migrated off the deprecated spellings.
    'legacy_mode',          # horizontal_loop_extent + number_of_openmp_threads
    'gfs_dim_aliases',      # GFS radiation/composition vertical dim aliases
    'legacy_auto_clone_constituents',  # original-capgen auto-clone path
})


# Per-kwarg default values.  Any name not listed here defaults to
# ``None`` -- the inherited "absent" sentinel original capgen's class
# also uses.  ``legacy_mode`` defaults to ``True`` because the bulk of
# CAM-SIMA's scheme metadata still spells the horizontal axis as
# ``horizontal_loop_extent`` (119 .meta files at last count) and the
# OpenMP thread count as ``number_of_openmp_threads``; the shim is
# silent on metadata that already uses the canonical capgen-ng names,
# so leaving it on costs nothing for migrated metadata.  Explicitly
# pass ``legacy_mode=False`` to disable.
_KWARG_DEFAULTS = {
    'legacy_mode': True,
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

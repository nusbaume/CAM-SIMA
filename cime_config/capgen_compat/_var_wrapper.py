"""Variable wrapper exposing original capgen's per-variable Python
surface on top of capgen's ``HostVarEntry`` / ``ResolvedArg``.

The 14-method surface ``write_init_files.py`` reads is implemented
uniformly across both backing types via the
:meth:`_VarWrapper.from_host_entry` and
:meth:`_VarWrapper.from_resolved_arg` factories.
"""

import re
from typing import List, Optional


_HORIZ_DIM_STDS: frozenset = frozenset({
    'horizontal_dimension',
    'horizontal_loop_extent',
})
_VERT_DIM_STDS: frozenset = frozenset({
    'vertical_layer_dimension',
    'vertical_interface_dimension',
})

# Sliced metadata local_name, e.g. ``q(:,:,index_of_X)``.  Group 1 is
# the bare identifier, group 2 is the comma-separated subscript inside
# the parens (matches the original Var.array_ref() shape).
_ARRAY_REF_RE = re.compile(r'^(\w+)\s*\(([^)]+)\)\s*$')


def _is_base_constituent_name(std_name: str, arg) -> bool:
    """True iff *std_name* names a base constituent species.

    Base species are the only constituent args the runtime can resolve by
    standard name through ``const_get_index``; see the ``advected``
    discussion in :meth:`_VarWrapper.from_resolved_arg`.  Everything else
    capgen routes through ``source == 'constituent'`` -- tendencies
    (``tendency_of_*``, stored in ``vars_layer_tend`` under the BASE
    name's index), ``index_of_*`` integers, the framework arrays/counts,
    and the register-phase properties array -- is not.

    The prefixes and the framework-name set are imported from capgen
    rather than duplicated: if capgen renames them this raises at import
    time instead of silently reclassifying every constituent arg.
    """
    from generator.suite_resolver import (
        _TEND_PREFIX, _INDEX_PREFIX, _FRAMEWORK_CONST_STDS,
    )
    if getattr(arg, 'is_constituent_arg', False):
        return False
    if std_name in _FRAMEWORK_CONST_STDS:
        return False
    return not (std_name.startswith(_TEND_PREFIX)
                or std_name.startswith(_INDEX_PREFIX))


class _Source:
    """Stand-in for ``Var.source`` from original capgen.

    Two attributes read by ``write_init_files.py``:

    * ``ptype`` -- ``'host'`` / ``'API'`` / ``'scheme'`` / ``'ddt'``.
      Cam-sima only branches on ``'host'``; everything else is treated
      as a non-host source.
    * ``name`` -- the Fortran module that exports the variable's
      Fortran symbol.
    """

    __slots__ = ('ptype', 'name')

    def __init__(self, ptype: str, name: Optional[str]):
        self.ptype = ptype
        self.name  = name

    def __repr__(self) -> str:
        return '_Source(ptype={!r}, name={!r})'.format(self.ptype, self.name)


class _VarWrapper:
    """Original-capgen-style variable wrapper.

    Construct via :meth:`from_host_entry` (host_dict path) or
    :meth:`from_resolved_arg` (call_list path).
    """

    __slots__ = (
        '_standard_name', '_local_name', '_intent', '_protected',
        '_advected', '_constituent',
        '_dimensions', '_source', '_call_expr',
        '_intrinsic_subnames',
        # ``_inner`` is the wrapper returned by :attr:`var`.  For a
        # DDT-walked entry it reports the access-path root as
        # ``local_name`` so ``hvar.var.get_prop_value('local_name')``
        # yields the symbol to USE-import; for a bare entry it is
        # ``self``.
        '_inner',
        # ``_local_subscript`` is the list of subscript tokens that
        # original capgen surfaced through ``array_ref()`` -- the
        # array-of-DDT element-resolution path.  Each token is either
        # ``':'`` (kept axis) or a CCPP standard name pointing at the
        # host-side index variable (e.g.
        # ``'index_of_potential_temperature'``).  Driven from
        # ``HostVarEntry.local_subscript``; empty for bare host vars.
        '_local_subscript',
    )

    def __init__(
        self,
        standard_name: str,
        local_name: str,
        intent: str,
        protected: bool,
        advected: bool,
        constituent: bool,
        dimensions: List[str],
        source: _Source,
        call_expr: Optional[str],
        intrinsic_subnames: Optional[List[str]],
        local_subscript: Optional[List[str]] = None,
    ):
        self._standard_name      = standard_name
        self._local_name         = local_name
        self._intent             = intent
        self._protected          = protected
        self._advected           = advected
        self._constituent        = constituent
        self._dimensions         = list(dimensions)
        self._source             = source
        self._call_expr          = call_expr
        self._intrinsic_subnames = intrinsic_subnames
        self._local_subscript    = list(local_subscript or [])
        # ``_inner`` defaults to self -- factories that need a
        # distinct inner-wrapper layer reassign it.
        self._inner              = self

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_host_entry(
        cls,
        entry,
        intrinsic_subnames: Optional[List[str]] = None,
        intent: str = '',
    ) -> '_VarWrapper':
        """Build a wrapper for a host-dict entry (``HostVarEntry``).

        *intent* is ``''`` for host_dict lookups (a host variable has no
        intent of its own).  The dimension-variable path in
        :class:`_cap_database.CapDatabase` passes ``'in'``: capgen tracks
        dimension references on ``ResolvedArg.used_dim_std_names``
        instead of emitting a call-list arg for them, but original capgen
        put those variables on the group call list, where
        ``write_init_files`` reads them as inputs.
        """
        # Control variables have module_name=None → ptype = 'API'
        # (capgen's framework-injected vars; cam-sima's
        # write_init_files filter ``ptype != 'host'`` includes them).
        #
        # Otherwise we need to distinguish two cases that capgen
        # collapsed into one ``type = host`` after the type=module
        # rename:
        #
        # * Registry-allocated module variables (original capgen's
        #   ``type = module``).  ``write_init_files.py`` needs to
        #   allocate + initialise these, so it expects
        #   ``ptype != 'host'``.  We tag them ``'module'``.
        # * Subroutine-arg host variables (original capgen's
        #   ``type = host``).  ``write_init_files.py`` skips these
        #   (the host's subroutine call supplies them) via
        #   ``ptype == 'host'``.
        #
        # The distinction is recovered from the
        # ``capgen_compat:original_type = module`` marker that
        # ``generate_registry_data.py`` writes alongside the rewritten
        # ``type = host`` line; metadata_table.py records the table
        # names in ``MODULE_ORIGIN_TABLE_NAMES``.
        if entry.module_name is None:
            ptype = 'API'
        else:
            from metadata_table import MODULE_ORIGIN_TABLE_NAMES
            # The HostVarEntry.module_name attribute carries the
            # Fortran module name -- which capgen defaults to the
            # metadata table name when no explicit override was
            # supplied.  generate_registry_data.py emits tables whose
            # name matches the Fortran module, so the same string
            # appears in both the entry's module_name and in our
            # MODULE_ORIGIN_TABLE_NAMES set.
            if entry.module_name.lower() in MODULE_ORIGIN_TABLE_NAMES:
                ptype = 'module'
            else:
                ptype = 'host'
        source = _Source(ptype=ptype, name=entry.module_name)
        # capgen's HostVarEntry has two distinct fields that
        # original capgen split across two property layers:
        #
        #  * ``entry.local_name``  -- the leaf identifier
        #    (e.g. ``theta`` for a DDT-component var).
        #    write_init_files reads this via the OUTER wrapper at
        #    sites that emit per-variable identifiers (the
        #    ``input_var_names`` table, the ic-name lookup).
        #  * ``entry.access_path`` -- the full Fortran expression
        #    (e.g. ``phys_state%theta``); its root token is the
        #    top-level USE'd symbol.  Original capgen exposed THAT
        #    via the INNER ``Var.local_name``, read at sites that
        #    emit ``use ..., only: <root>`` statements
        #    (``hvar.var.get_prop_value('local_name')``).
        #
        # Capture the root token here so :attr:`var` can return an
        # inner wrapper that reports it as ``local_name``.
        # Leaf identifier (outer wrapper's ``local_name``).
        leaf_name = entry.local_name
        # Top-level / root symbol for the use-only emit path
        # (inner ``var.local_name``).  Strip everything after the first
        # ``%`` or ``(`` in the access path.
        root_name = leaf_name
        if entry.access_path:
            ap = entry.access_path.split('%', 1)[0].split('(', 1)[0]
            ap = ap.strip()
            if ap:
                root_name = ap
        # ``local_subscript`` carries the array-of-DDT element-index
        # tokens (e.g. ``[':', ':', 'index_of_potential_temperature']``)
        # captured by capgen at parse time but not surfaced through
        # any of the wrapper's default fields.  Pass it through so
        # ``array_ref()`` and ``call_string()`` can synthesise the
        # sliced spelling original capgen used.
        local_subscript = list(getattr(entry, 'local_subscript', None) or [])
        wrapper = cls(
            standard_name      = entry.standard_name,
            local_name         = leaf_name,
            intent             = intent,
            protected          = bool(entry.protected),
            advected           = False,
            constituent        = False,
            dimensions         = list(entry.dimensions),
            source             = source,
            call_expr          = entry.access_path,
            intrinsic_subnames = intrinsic_subnames,
            local_subscript    = local_subscript,
        )
        # Pre-build the inner ``.var`` wrapper that reports the root
        # symbol as local_name.  If leaf == root (no DDT walk), reuse
        # ``self`` for ``.var`` so identity comparisons still hold.
        if root_name == leaf_name:
            wrapper._inner = wrapper
        else:
            wrapper._inner = cls(
                standard_name      = entry.standard_name,
                local_name         = root_name,
                intent             = intent,
                protected          = bool(entry.protected),
                advected           = False,
                constituent        = False,
                dimensions         = list(entry.dimensions),
                source             = source,
                call_expr          = entry.access_path,
                intrinsic_subnames = intrinsic_subnames,
                local_subscript    = local_subscript,
            )
            wrapper._inner._inner = wrapper._inner
        return wrapper

    @classmethod
    def from_resolved_arg(cls, arg) -> '_VarWrapper':
        """Build a wrapper for a scheme call-list arg (``ResolvedArg``)."""
        ptype_map = {
            'host':        'host',
            'control':     'API',
            'suite':       'scheme',
            'constituent': 'API',
        }
        ptype = ptype_map.get(arg.source, 'API')
        source = _Source(ptype=ptype, name=arg.module_name)
        # write_init_files keys constituent handling -- skip USE-import and
        # skip the initial-conditions read; the constituents object supplies
        # the value at runtime -- on the call-list var's ``advected`` /
        # ``constituent`` property.  Capgen tags EVERY framework-provided
        # constituent arg with ``source == 'constituent'``: base species
        # (vars_layer), constituent tendencies (vars_layer_tend), the
        # framework arrays/counts, ``index_of_*`` integers, and the
        # register-phase ccpp_constituent_properties_t arg.  The per-arg
        # ``is_constituent`` / ``is_constituent_arg`` flags are a strict
        # SUBSET: they are set only when the SCHEME ITSELF flagged the arg
        # (advected / constituent / molar_mass) or it is the register array.
        # An *inferred* consumer -- e.g. a sima_diagnostics scheme reading
        # ``tendency_of_<X>`` (intent=in) without re-flagging it (rule b) --
        # resolves to ``source == 'constituent'`` yet carries
        # ``is_constituent == False``, because whether a standard name is a
        # constituent is the host's decision, not the consumer's.  Keying on
        # the source (not the consumer's own flag) closes that gap so the arg
        # is routed through the constituents object instead of being
        # mis-flagged as a missing required host variable.
        is_constituent = (
            arg.source == 'constituent'
            or bool(arg.is_constituent)
            or bool(arg.is_constituent_arg)
        )
        # ``advected`` is a STRICT subset of ``constituent``.
        # write_init_files excludes advected vars from phys_var_stdnames
        # because the runtime resolves them through the constituent
        # object -- ``const_get_index(std_name)``.  That lookup only
        # succeeds for a base constituent: a tendency lives in
        # ``vars_layer_tend`` keyed by the BASE name's index, an
        # ``index_of_*`` integer and the framework arrays/counts are not
        # constituents at all, and the register-phase properties array is
        # framework-internal.  Reporting those as advected drops them
        # from phys_var_stdnames with no build-time error, and the
        # runtime initialization check then aborts with "Required
        # variables missing from registered list of input variables".
        #
        # Known imprecision: a base constituent flagged ``constituent``
        # but not ``advected`` is still reported advected here, because
        # ResolvedArg does not carry the metadata's ``advected`` flag
        # (only the merged ``is_constituent``).  That direction is the
        # safe one -- the variable is in the runtime constituent table
        # either way, it just loses its registered IC-file input names.
        # Exposing ``advected`` on ResolvedArg would let this be exact.
        is_advected = is_constituent and _is_base_constituent_name(
            arg.standard_name, arg)
        return cls(
            standard_name      = arg.standard_name,
            local_name         = arg.scheme_local_name,
            intent             = arg.intent,
            protected          = False,
            advected           = is_advected,
            constituent        = is_constituent,
            dimensions         = list(arg.scheme_dimensions),
            source             = source,
            call_expr          = arg.call_expr,
            intrinsic_subnames = None,
        )

    # ------------------------------------------------------------------
    # Original-capgen accessors
    # ------------------------------------------------------------------

    _PROP_MAP = {
        'standard_name': '_standard_name',
        'local_name':    '_local_name',
        'intent':        '_intent',
        'protected':     '_protected',
        'advected':      '_advected',
        'constituent':   '_constituent',
    }

    def get_prop_value(self, prop: str):
        """Return the named property.

        Raises ``KeyError`` for unknown props -- original capgen returned
        ``None``; we raise so a new write_init_files property request
        surfaces here, not as a silent mis-branch downstream.
        """
        attr = self._PROP_MAP.get(prop)
        if attr is None:
            raise KeyError(
                "capgen_compat _VarWrapper.get_prop_value: unknown "
                "property '{}'; supported names are {}".format(
                    prop, sorted(self._PROP_MAP)
                )
            )
        return getattr(self, attr)

    @property
    def source(self) -> _Source:
        return self._source

    @property
    def var(self) -> '_VarWrapper':
        """write_init_files:678 does ``hvar.var.get_prop_value(...)``.

        Original capgen exposed a dictionary-wrapper around an inner
        ``Var``; ``.var`` peeled the outer layer off.  CAM-SIMA uses
        the inner layer at sites that emit USE statements -- for a
        DDT-walked host_dict entry the inner ``local_name`` is the
        ROOT symbol of the access path (the thing to USE-import),
        while the outer wrapper reports the leaf component name.
        """
        return self._inner

    # ------------------------------------------------------------------
    # Dimension predicates
    # ------------------------------------------------------------------

    def get_dimensions(self) -> List[str]:
        return list(self._dimensions)

    def has_horizontal_dimension(self) -> bool:
        return any(self._is_horiz(d) for d in self._dimensions)

    def has_vertical_dimension(self) -> str:
        """Truthy std_name when a vertical dim is present, ``''`` otherwise."""
        for d in self._dimensions:
            stripped = self._strip_bounds(d)
            if stripped in _VERT_DIM_STDS:
                return stripped
        return ''

    @staticmethod
    def _is_horiz(dim: str) -> bool:
        return _VarWrapper._strip_bounds(dim) in _HORIZ_DIM_STDS

    @staticmethod
    def _strip_bounds(dim: str) -> str:
        if ':' in dim:
            return dim.split(':', 1)[1].strip()
        return dim.strip()

    # ------------------------------------------------------------------
    # Array reference + intrinsic-elements
    # ------------------------------------------------------------------

    def array_ref(self) -> Optional[re.Match]:
        """Return a regex match against a sliced ``local_name``.

        Two cases produce a match:

        1. ``local_name`` already carries a parenthesised subscript
           (the metadata declared the var with a sliced spelling such
           as ``q(:,:,index_of_X)``).
        2. ``local_subscript`` carries the array-of-DDT index tokens
           captured by capgen's resolver (the registry-emitted
           sliced spelling, e.g.
           ``[':', ':', 'index_of_potential_temperature']``).  We
           synthesise a ``local_name(s1, s2, ...)`` string and run the
           same regex on it -- ``group(2)`` then carries the
           subscript-token list the recursive
           ``write_init_files.collect_host_var_imports`` walker needs
           to drive its ``host_dict.find_variable(...)`` loop.
        """
        if self._local_subscript:
            synthetic = '{}({})'.format(
                self._local_name,
                ', '.join(self._local_subscript),
            )
            m = _ARRAY_REF_RE.match(synthetic)
            if m is not None:
                return m
        return _ARRAY_REF_RE.match(self._local_name)

    def intrinsic_elements(self) -> Optional[List[str]]:
        """Sub-element std_names for array-of-DDT entries.

        ``None`` (not ``[]``) for plain variables; write_init_files
        distinguishes via ``isinstance(ielem, list)``.
        """
        return self._intrinsic_subnames

    # ------------------------------------------------------------------
    # Call-site rendering
    # ------------------------------------------------------------------

    def call_string(self, host_dict) -> str:
        """Return the Fortran call-site expression.

        Wrappers built from ResolvedArg have the baked
        ``call_expr``; host-dict-only wrappers use ``access_path``.

        For array-of-DDT element entries (``local_subscript``
        non-empty), append the resolved subscript: each
        non-``':'`` token is looked up in *host_dict* and replaced
        with the resolver's local Fortran name (e.g.
        ``'index_of_potential_temperature'`` → ``'ix_theta'``).
        Tokens that don't resolve are passed through verbatim, which
        matches original capgen's behaviour for unknown indices.

        The result is lowercased to match original capgen's emission
        convention (its Var.local_name was lowercased at parse time,
        so every cap-emitted Fortran identifier came out lower-case).
        capgen preserves the metadata's case verbatim; lowercasing
        here keeps the generated phys_input / phys_check Fortran
        byte-equal to the committed CAM-SIMA goldens.  Fortran is
        case-insensitive so the compiled behaviour is unaffected.
        """
        base = self._call_expr or self._local_name
        if not self._local_subscript:
            return base.lower()
        resolved = []
        for tok in self._local_subscript:
            if tok == ':':
                resolved.append(':')
                continue
            hv = None
            if host_dict is not None:
                hv = host_dict.find_variable(tok)
            if hv is not None:
                resolved.append(hv.get_prop_value('local_name'))
            else:
                resolved.append(tok)
        return '{}({})'.format(base, ', '.join(resolved)).lower()

    def __repr__(self) -> str:
        return ('_VarWrapper(standard_name={!r}, local_name={!r}, '
                'source.ptype={!r})'.format(
                    self._standard_name, self._local_name,
                    self._source.ptype,
                ))

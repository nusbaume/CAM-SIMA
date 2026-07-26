"""``CapDatabase`` facade -- host_model_dict + call_list(phase) on top
of capgen's flat host_dict and per-(scheme, phase) ResolvedCall map.
"""

from collections import OrderedDict
from typing import Dict, List, Optional, Set

from _var_wrapper import _VarWrapper


# Map original-capgen phase names → capgen phase keys.  capgen
# uses ``init`` / ``final`` / ``timestep_init``; original capgen uses
# ``initialize`` / ``finalize`` / ``timestep_initial``.  Accept either
# spelling so CAM-SIMA can keep its phase iteration unchanged.
_PHASE_ALIAS = {
    'initialize':       'init',
    'finalize':         'final',
    'timestep_initial': 'timestep_init',
    # Identity entries for capgen's canonical names.
    'register':         'register',
    'init':             'init',
    'timestep_init':    'timestep_init',
    'run':              'run',
    'timestep_final':   'timestep_final',
    'final':            'final',
}


class _HostDict:
    """Host-variable dictionary with ``find_variable(stdname)`` lookup.

    Wraps every ``HostVarEntry`` lazily into a :class:`_VarWrapper` and
    caches the wrapper so the recursive constituent traversal in
    ``write_init_files._find_and_add_host_variable`` reuses the same
    wrapper identity.
    """

    def __init__(self, host_dict):
        self._host_dict = host_dict
        self._cache: Dict[str, _VarWrapper] = {}

    def find_variable(self, stdname: str) -> Optional[_VarWrapper]:
        """Return a wrapper for *stdname*, or ``None``.

        Case-insensitive (capgen stores std_names lowercased).
        """
        if stdname is None:
            return None
        key = stdname.lower()
        if key in self._cache:
            return self._cache[key]
        entry = self._host_dict.get(key)
        if entry is None:
            return None
        wrapper = _VarWrapper.from_host_entry(entry)
        self._cache[key] = wrapper
        return wrapper

    def find_dimension_variable(self, stdname: str) -> Optional[_VarWrapper]:
        """Return an ``intent='in'`` wrapper for a *registry* dimension var.

        Used for the ``ResolvedArg.used_dim_std_names`` entries that
        :class:`CapDatabase` surfaces on the call list (see
        :meth:`CapDatabase._collect_dims`).  Returns ``None`` unless the
        variable resolves to a registry-allocated module variable
        (``ptype == 'module'``).

        The two rejected categories are deliberate:

        * ``ptype == 'host'`` — host-structure dims such as
          ``horizontal_dimension`` / ``vertical_layer_dimension``.
          ``write_init_files._find_and_add_host_variable`` drops these
          anyway, so surfacing them would be a no-op at best.
        * ``ptype == 'API'`` — control vars (``horizontal_loop_begin`` /
          ``horizontal_loop_end``).  Under original capgen these were
          plain host loop variables (``ptype == 'host'``) and were
          filtered out; CAM-SIMA only declares them in a ``type =
          control`` table because capgen requires it.  They are not
          registry variables and must not reach ``phys_var_stdnames``.
        """
        wrapper = self.find_variable(stdname)
        if wrapper is None or wrapper.source.ptype != 'module':
            return None
        entry = self._host_dict.get(stdname.lower())
        return _VarWrapper.from_host_entry(entry, intent='in')


class _CallList:
    """Per-phase iterable of scheme-arg wrappers.

    *dim_vars* are already-built wrappers for the registry dimension
    variables the phase's args reference; they follow the scheme args in
    the returned list.
    """

    def __init__(self, args: List, dim_vars: Optional[List] = None):
        self._args = list(args)
        self._dim_vars = list(dim_vars or [])
        self._wrappers: Optional[List[_VarWrapper]] = None

    def variable_list(self) -> List[_VarWrapper]:
        if self._wrappers is None:
            self._wrappers = [_VarWrapper.from_resolved_arg(a)
                              for a in self._args]
            self._wrappers.extend(self._dim_vars)
        return list(self._wrappers)


_EMPTY_CALL_LIST = _CallList([])


def _walk_calls(items):
    """Yield every leaf scheme call in *items*, recursing into subcycles.

    Duck-typed (no isinstance checks against capgen resolver classes)
    so adapter tests can drive the facade with stub objects that carry
    just ``.args`` / ``.calls`` -- the two attributes the aggregator
    reads.
    """
    for item in items:
        if hasattr(item, 'args'):
            yield item
        elif hasattr(item, 'calls'):
            yield from _walk_calls(item.calls)


class CapDatabase:
    """Original-capgen-style ``cap_database`` facade.

    Built by :func:`_runner.capgen` from capgen's flat ``host_dict``
    plus an iterable of ``SuiteResolution`` objects (one per suite).
    Aggregates per-phase ResolvedArg lists across every suite and
    exposes them through :meth:`call_list`.
    """

    def __init__(self, host_dict, suite_resolutions):
        self._host = _HostDict(host_dict)

        # Aggregate ResolvedArgs per phase, dedup by
        # (scheme_name, phase, standard_name).
        seen: Set = set()
        per_phase: Dict[str, List] = OrderedDict()
        per_phase_dims: Dict[str, List[str]] = OrderedDict()
        for sr in suite_resolutions:
            for group in sr.groups:
                for phase, items in group.phase_calls.items():
                    for rc in _walk_calls(items):
                        self._collect(rc, per_phase, seen, per_phase_dims)
            # Suite-level <init>/<final> hooks count as calls too.
            if getattr(sr, 'suite_init_call', None) is not None:
                self._collect(sr.suite_init_call, per_phase, seen,
                              per_phase_dims)
            if getattr(sr, 'suite_final_call', None) is not None:
                self._collect(sr.suite_final_call, per_phase, seen,
                              per_phase_dims)

        self._per_phase = per_phase
        self._per_phase_dims = per_phase_dims

    # ResolvedArg.source values capgen emits.  Original capgen's
    # ``call_list(phase).variable_list()`` contract is *host-facing*:
    # every entry must be lookup-able in the host_dict (or, for
    # is_const-tagged args, in the constituent system).  Capgen's
    # resolver explicitly carves out a third category --
    # ``source='suite'`` -- for vars produced by one scheme and
    # consumed by another within the same suite (suite_data).  Those
    # never appear in the host_dict by design and must not surface on
    # the call list, otherwise ``write_init_files.gather_ccpp_req_vars``
    # mis-flags them as "missing required host variables".  Drop them
    # here.
    _SUITE_INTERNAL_SOURCES = frozenset({'suite'})

    @classmethod
    def _collect(cls, rc, per_phase: Dict[str, List], seen: Set,
                 per_phase_dims: Optional[Dict[str, List[str]]] = None) -> None:
        phase = rc.phase
        bucket = per_phase.setdefault(phase, [])
        dim_bucket = (None if per_phase_dims is None
                      else per_phase_dims.setdefault(phase, []))
        for arg in rc.args:
            if getattr(arg, 'source', None) in cls._SUITE_INTERNAL_SOURCES:
                continue
            key = (rc.scheme_name, phase, arg.standard_name)
            if key in seen:
                continue
            seen.add(key)
            bucket.append(arg)
            cls._collect_dims(arg, dim_bucket)

    @staticmethod
    def _collect_dims(arg, dim_bucket: Optional[List[str]]) -> None:
        """Record the dimension std names *arg* references, in order.

        Capgen tracks dimension variables on
        ``ResolvedArg.used_dim_std_names`` and does not emit a call-list
        arg for them.  Original capgen instead added every dimension
        variable to the group's call list, which is where
        ``write_init_files.gather_ccpp_req_vars`` picks up registry
        variables that appear *only* as someone else's dimension (e.g. a
        registry ``band_number`` used as the second dim of a scheme arg).
        Without this, such a variable is silently absent from
        ``phys_var_stdnames`` — no build error, but the runtime
        initialization check cannot resolve it.

        ``used_dim_std_names`` is not restricted to dimensions: it also
        carries subscript *index* references for array-of-DDT element
        resolution (``index_of_potential_temperature`` and friends).
        Original capgen did not register those, so intersect with the
        arg's declared dimensions — the names that are genuinely an axis
        of the variable.  Dimension entries may be ranges
        (``ccpp_constant_one:vertical_layer_dimension``), so split them.

        Which of the surviving names actually reach the call list is
        decided later by :meth:`_HostDict.find_dimension_variable`.
        """
        if dim_bucket is None:
            return
        used = getattr(arg, 'used_dim_std_names', None) or ()
        if not used:
            return
        for dim in getattr(arg, 'scheme_dimensions', None) or ():
            for token in str(dim).split(':'):
                token = token.strip()
                if token in used and token not in dim_bucket:
                    dim_bucket.append(token)

    def host_model_dict(self) -> _HostDict:
        return self._host

    def call_list(self, phase: str) -> _CallList:
        """Return the per-phase call list.

        Accepts capgen phase names (``init`` / ``final``) and
        original-capgen names (``initialize`` / ``finalize``).
        Unknown phases return an empty call list rather than raising
        -- write_init_files iterates every phase and would otherwise
        need a try/except per iteration.
        """
        canonical = _PHASE_ALIAS.get(phase, phase)
        args = self._per_phase.get(canonical, [])
        if not args:
            return _EMPTY_CALL_LIST
        dim_vars = []
        for std_name in self._per_phase_dims.get(canonical, []):
            wrapper = self._host.find_dimension_variable(std_name)
            if wrapper is not None:
                dim_vars.append(wrapper)
        return _CallList(args, dim_vars)

    def __repr__(self) -> str:
        sizes = {p: len(v) for p, v in self._per_phase.items()}
        return 'CapDatabase(phases={})'.format(sizes)

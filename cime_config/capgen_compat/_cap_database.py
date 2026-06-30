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


class _CallList:
    """Per-phase iterable of scheme-arg wrappers."""

    def __init__(self, args: List):
        self._args = list(args)
        self._wrappers: Optional[List[_VarWrapper]] = None

    def variable_list(self) -> List[_VarWrapper]:
        if self._wrappers is None:
            self._wrappers = [_VarWrapper.from_resolved_arg(a)
                              for a in self._args]
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
        for sr in suite_resolutions:
            for group in sr.groups:
                for phase, items in group.phase_calls.items():
                    for rc in _walk_calls(items):
                        self._collect(rc, per_phase, seen)
            # Suite-level <init>/<final> hooks count as calls too.
            if getattr(sr, 'suite_init_call', None) is not None:
                self._collect(sr.suite_init_call, per_phase, seen)
            if getattr(sr, 'suite_final_call', None) is not None:
                self._collect(sr.suite_final_call, per_phase, seen)

        self._per_phase = per_phase

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
    def _collect(cls, rc, per_phase: Dict[str, List], seen: Set) -> None:
        phase = rc.phase
        bucket = per_phase.setdefault(phase, [])
        for arg in rc.args:
            if getattr(arg, 'source', None) in cls._SUITE_INTERNAL_SOURCES:
                continue
            key = (rc.scheme_name, phase, arg.standard_name)
            if key in seen:
                continue
            seen.add(key)
            bucket.append(arg)

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
        return _CallList(args)

    def __repr__(self) -> str:
        sizes = {p: len(v) for p, v in self._per_phase.items()}
        return 'CapDatabase(phases={})'.format(sizes)

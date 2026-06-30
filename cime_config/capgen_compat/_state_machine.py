"""Minimal CCPP state machine for write_init_files.

Original capgen's ``ccpp_state_machine`` carries a full ``StateMachine``
implementation; the only piece ``write_init_files.py`` actually needs
is ``.transitions()`` returning the per-phase identifier list.

Phase names match capgen's:

    register, init, timestep_init, run, timestep_final, final

The :class:`CapDatabase.call_list` lookup accepts the original-capgen
spellings (``initialize``, ``finalize``, ``timestep_initial``) too, so
existing CAM-SIMA fixtures iterating either set of names keep working.
"""

from typing import List


_PHASES: List[str] = [
    'register',
    'init',
    'timestep_init',
    'run',
    'timestep_final',
    'final',
]


class _StateMachine:
    """Pared-down stand-in for ``ccpp_state_machine.StateMachine``."""

    def __init__(self, phases: List[str]):
        self._phases = list(phases)

    def transitions(self) -> List[str]:
        """Return the ordered list of CCPP scheme phases.

        ``write_init_files.py`` uses this at
        ``src/data/write_init_files.py:334``::

            for phase in CCPP_STATE_MACH.transitions():
                for cvar in cap_database.call_list(phase).variable_list():
                    ...

        Order matches the order CAM-SIMA expects to encounter scheme
        args in (init before run, etc.).
        """
        return list(self._phases)


CCPP_STATE_MACH = _StateMachine(_PHASES)

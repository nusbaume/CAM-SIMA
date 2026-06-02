"""Tests for ``capgen_compat._state_machine.CCPP_STATE_MACH``."""

import unittest

from _state_machine import CCPP_STATE_MACH


class TestCCPPStateMachine(unittest.TestCase):

    def test_transitions_returns_list(self):
        phases = CCPP_STATE_MACH.transitions()
        self.assertIsInstance(phases, list)
        self.assertGreater(len(phases), 0)

    def test_transitions_include_canonical_phases(self):
        phases = CCPP_STATE_MACH.transitions()
        for expected in ('register', 'init', 'run', 'final'):
            self.assertIn(expected, phases)

    def test_transitions_returns_new_list_each_call(self):
        first  = CCPP_STATE_MACH.transitions()
        first.append('mutated')
        third = CCPP_STATE_MACH.transitions()
        self.assertNotIn('mutated', third)


if __name__ == '__main__':
    unittest.main()

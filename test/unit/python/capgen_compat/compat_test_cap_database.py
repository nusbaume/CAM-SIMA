"""Tests for ``capgen_compat._cap_database.CapDatabase``."""

import unittest

from _cap_database import CapDatabase, _PHASE_ALIAS
from compat_test_var_wrapper import _StubHostEntry, _StubResolvedArg


class _StubResolvedCall:
    def __init__(self, scheme_name, phase, args):
        self.scheme_name = scheme_name
        self.phase       = phase
        self.args        = args


class _StubResolvedGroup:
    def __init__(self, group_name, phase_calls):
        self.group_name  = group_name
        self.phase_calls = phase_calls


class _StubSuiteResolution:
    def __init__(self, suite_name, groups,
                 suite_init_call=None, suite_final_call=None):
        self.suite_name       = suite_name
        self.groups           = groups
        self.suite_init_call  = suite_init_call
        self.suite_final_call = suite_final_call


def _hd(*entries):
    return {e.standard_name.lower(): e for e in entries}


class TestHostDict(unittest.TestCase):

    def test_find_variable_hit(self):
        db = CapDatabase(_hd(_StubHostEntry(standard_name='pi')), [])
        self.assertIsNotNone(db.host_model_dict().find_variable('pi'))

    def test_find_variable_case_insensitive(self):
        db = CapDatabase(_hd(_StubHostEntry(standard_name='pi')), [])
        self.assertIsNotNone(db.host_model_dict().find_variable('PI'))

    def test_find_variable_miss_returns_none(self):
        db = CapDatabase(_hd(), [])
        self.assertIsNone(db.host_model_dict().find_variable('missing'))


class TestCallList(unittest.TestCase):

    def _suite(self, phase):
        rc = _StubResolvedCall('s', phase,
                               [_StubResolvedArg(standard_name='x')])
        return _StubSuiteResolution(
            's', [_StubResolvedGroup('g', {phase: [rc]})])

    def test_call_list_returns_phase_args(self):
        db = CapDatabase({}, [self._suite('run')])
        self.assertEqual(len(db.call_list('run').variable_list()), 1)

    def test_call_list_accepts_original_capgen_names(self):
        db = CapDatabase({}, [self._suite('init')])
        self.assertEqual(len(db.call_list('initialize').variable_list()), 1)

    def test_call_list_unknown_phase_returns_empty(self):
        db = CapDatabase({}, [self._suite('run')])
        self.assertEqual(db.call_list('not_a_phase').variable_list(), [])

    def test_call_list_dedupes(self):
        rc = _StubResolvedCall('s', 'run',
                               [_StubResolvedArg(standard_name='shared')])
        g1 = _StubResolvedGroup('g1', {'run': [rc]})
        g2 = _StubResolvedGroup('g2', {'run': [rc]})
        sr1 = _StubSuiteResolution('s1', [g1])
        sr2 = _StubSuiteResolution('s2', [g2])
        db = CapDatabase({}, [sr1, sr2])
        self.assertEqual(len(db.call_list('run').variable_list()), 1)

    def test_suite_init_final_calls_included(self):
        init_call = _StubResolvedCall('init_sch', 'init',
                                      [_StubResolvedArg(standard_name='a')])
        sr = _StubSuiteResolution('s', [], suite_init_call=init_call)
        db = CapDatabase({}, [sr])
        self.assertEqual(len(db.call_list('init').variable_list()), 1)


class TestPhaseAlias(unittest.TestCase):

    def test_original_capgen_aliases(self):
        self.assertEqual(_PHASE_ALIAS['initialize'], 'init')
        self.assertEqual(_PHASE_ALIAS['finalize'], 'final')


if __name__ == '__main__':
    unittest.main()

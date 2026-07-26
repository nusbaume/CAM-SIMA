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

    def test_call_list_drops_suite_internal_args(self):
        # Capgen tags vars produced by one scheme and consumed by
        # another within the same suite (e.g. air_potential_temperature,
        # dimensionless_exner_function, scheme_name in CAM-SIMA's
        # kessler suite) with source='suite'.  Those must not appear
        # on the call list -- original capgen's contract treats every
        # call-list entry as host-required, and
        # write_init_files.gather_ccpp_req_vars would mis-flag them
        # as "missing required host variables".  source='host' /
        # 'control' / 'constituent' all stay.
        rc = _StubResolvedCall('s', 'run', [
            _StubResolvedArg(standard_name='from_host', source='host'),
            _StubResolvedArg(standard_name='from_suite', source='suite'),
            _StubResolvedArg(standard_name='from_control', source='control'),
            _StubResolvedArg(standard_name='from_const', source='constituent'),
        ])
        sr = _StubSuiteResolution(
            's', [_StubResolvedGroup('g', {'run': [rc]})])
        db = CapDatabase({}, [sr])
        stds = {w.get_prop_value('standard_name')
                for w in db.call_list('run').variable_list()}
        self.assertEqual(stds, {'from_host', 'from_control', 'from_const'})


class TestCallListDimensionVariables(unittest.TestCase):
    """Registry variables that appear only as another variable's dimension.

    Capgen records them on ``ResolvedArg.used_dim_std_names`` and emits no
    call-list arg; original capgen put them on the group call list, which
    is where ``write_init_files`` finds the registry variables it must
    register.  The facade restores that, but only for registry
    (``ptype == 'module'``) variables.
    """

    def _db(self, host_entries, arg):
        rc = _StubResolvedCall('s', 'run', [arg])
        sr = _StubSuiteResolution(
            's', [_StubResolvedGroup('g', {'run': [rc]})])
        return CapDatabase(_hd(*host_entries), [sr])

    def _stds(self, db):
        return {w.get_prop_value('standard_name')
                for w in db.call_list('run').variable_list()}

    def _registry_entry(self, standard_name):
        # ptype == 'module' requires the module name to be registered as
        # a registry-generated table (the capgen_compat:original_type
        # marker path).
        from metadata_table import MODULE_ORIGIN_TABLE_NAMES
        MODULE_ORIGIN_TABLE_NAMES.add('physics_types')
        self.addCleanup(MODULE_ORIGIN_TABLE_NAMES.discard, 'physics_types')
        return _StubHostEntry(standard_name=standard_name,
                              local_name='band_no',
                              access_path='band_no',
                              module_name='physics_types')

    def test_registry_dimension_var_on_call_list(self):
        arg = _StubResolvedArg(
            standard_name='air_pressure_at_sea_level',
            scheme_dimensions=['horizontal_dimension', 'band_number'],
            used_dim_std_names={'horizontal_dimension', 'band_number'})
        db = self._db([self._registry_entry('band_number')], arg)
        self.assertIn('band_number', self._stds(db))

    def test_registry_dimension_var_is_an_input(self):
        arg = _StubResolvedArg(
            standard_name='air_pressure_at_sea_level',
            scheme_dimensions=['band_number'],
            used_dim_std_names={'band_number'})
        db = self._db([self._registry_entry('band_number')], arg)
        dim = [w for w in db.call_list('run').variable_list()
               if w.get_prop_value('standard_name') == 'band_number'][0]
        self.assertEqual(dim.get_prop_value('intent'), 'in')

    def test_host_structure_dimension_not_on_call_list(self):
        # ptype == 'host': write_init_files skips these anyway.
        entry = _StubHostEntry(standard_name='horizontal_dimension',
                               module_name='simple_host')
        arg = _StubResolvedArg(
            standard_name='air_pressure_at_sea_level',
            scheme_dimensions=['horizontal_dimension'],
            used_dim_std_names={'horizontal_dimension'})
        db = self._db([entry], arg)
        self.assertNotIn('horizontal_dimension', self._stds(db))

    def test_control_dimension_not_on_call_list(self):
        # module_name=None → ptype 'API'.  horizontal_loop_begin/end are
        # control vars only because capgen requires the table type; they
        # are not registry variables.
        entry = _StubHostEntry(standard_name='horizontal_loop_begin',
                               module_name=None)
        arg = _StubResolvedArg(
            standard_name='air_pressure_at_sea_level',
            scheme_dimensions=['horizontal_loop_begin:horizontal_loop_end'],
            used_dim_std_names={'horizontal_loop_begin'})
        db = self._db([entry], arg)
        self.assertNotIn('horizontal_loop_begin', self._stds(db))

    def test_subscript_index_not_on_call_list(self):
        # used_dim_std_names also carries array-of-DDT element indices.
        # They are not dimensions of the arg, so they must not register.
        arg = _StubResolvedArg(
            standard_name='air_pressure_at_sea_level',
            scheme_dimensions=['horizontal_dimension'],
            used_dim_std_names={'index_of_potential_temperature'})
        db = self._db(
            [self._registry_entry('index_of_potential_temperature')], arg)
        self.assertNotIn('index_of_potential_temperature', self._stds(db))

    def test_dimension_var_deduped_across_args(self):
        rc = _StubResolvedCall('s', 'run', [
            _StubResolvedArg(standard_name='a',
                             scheme_dimensions=['band_number'],
                             used_dim_std_names={'band_number'}),
            _StubResolvedArg(standard_name='b',
                             scheme_dimensions=['band_number'],
                             used_dim_std_names={'band_number'}),
        ])
        sr = _StubSuiteResolution(
            's', [_StubResolvedGroup('g', {'run': [rc]})])
        db = CapDatabase(_hd(self._registry_entry('band_number')), [sr])
        stds = [w.get_prop_value('standard_name')
                for w in db.call_list('run').variable_list()]
        self.assertEqual(stds.count('band_number'), 1)


class TestPhaseAlias(unittest.TestCase):

    def test_original_capgen_aliases(self):
        self.assertEqual(_PHASE_ALIAS['initialize'], 'init')
        self.assertEqual(_PHASE_ALIAS['finalize'], 'final')


if __name__ == '__main__':
    unittest.main()

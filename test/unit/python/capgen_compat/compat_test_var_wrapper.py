"""Tests for ``capgen_compat._var_wrapper._VarWrapper``."""

import unittest

from _var_wrapper import _VarWrapper


class _StubHostEntry:
    def __init__(self, standard_name='pi', local_name='con_pi',
                 access_path='con_pi', module_name='scm_physical_constants',
                 type='real', kind='dp', units='none',
                 dimensions=(), protected=True, optional=False,
                 active='', local_subscript=None, allocatable=False,
                 top_at_one=False):
        self.standard_name   = standard_name
        self.local_name      = local_name
        self.access_path     = access_path
        self.module_name     = module_name
        self.type            = type
        self.kind            = kind
        self.units           = units
        self.dimensions      = list(dimensions)
        self.protected       = protected
        self.optional        = optional
        self.active          = active
        self.local_subscript = local_subscript
        self.allocatable     = allocatable
        self.top_at_one      = top_at_one


class _StubResolvedArg:
    def __init__(self, standard_name='pi', scheme_local_name='con_pi',
                 intent='in', source='host', call_expr='con_pi',
                 module_name='scm_physical_constants',
                 scheme_dimensions=(),
                 is_constituent=False, is_constituent_arg=False):
        self.standard_name      = standard_name
        self.scheme_local_name  = scheme_local_name
        self.intent             = intent
        self.source             = source
        self.call_expr          = call_expr
        self._module_name       = module_name
        self.scheme_dimensions  = list(scheme_dimensions)
        self.is_constituent     = is_constituent
        self.is_constituent_arg = is_constituent_arg

    @property
    def module_name(self):
        return self._module_name


class TestFromHostEntry(unittest.TestCase):

    def test_basic_properties(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(protected=True))
        self.assertEqual(w.get_prop_value('standard_name'), 'pi')
        self.assertEqual(w.get_prop_value('local_name'), 'con_pi')
        self.assertTrue(w.get_prop_value('protected'))
        self.assertFalse(w.get_prop_value('advected'))

    def test_source_host_ptype_when_module_name_set(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(module_name='m'))
        self.assertEqual(w.source.ptype, 'host')

    def test_source_api_ptype_for_control_var(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(module_name=None))
        self.assertEqual(w.source.ptype, 'API')

    def test_array_ref(self):
        w = _VarWrapper.from_host_entry(
            _StubHostEntry(local_name='q(:,:,index_of_water)'))
        m = w.array_ref()
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'q')

    def test_dimension_predicates(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(
            dimensions=['horizontal_dimension', 'vertical_layer_dimension']))
        self.assertTrue(w.has_horizontal_dimension())
        self.assertEqual(w.has_vertical_dimension(), 'vertical_layer_dimension')

    def test_var_returns_self(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry())
        self.assertIs(w.var, w)

    def test_unknown_prop_raises(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry())
        with self.assertRaises(KeyError):
            w.get_prop_value('not_a_property')


class TestFromResolvedArg(unittest.TestCase):

    def test_intent_preserved(self):
        w = _VarWrapper.from_resolved_arg(_StubResolvedArg(intent='inout'))
        self.assertEqual(w.get_prop_value('intent'), 'inout')

    def test_constituent_classification(self):
        w = _VarWrapper.from_resolved_arg(
            _StubResolvedArg(is_constituent=True))
        self.assertTrue(w.get_prop_value('advected'))
        self.assertTrue(w.get_prop_value('constituent'))

    def test_call_string_returns_resolved_expr(self):
        w = _VarWrapper.from_resolved_arg(
            _StubResolvedArg(call_expr='gfs_statein(lb:ub, 1:nlev)'))
        self.assertEqual(w.call_string(None),
                         'gfs_statein(lb:ub, 1:nlev)')


if __name__ == '__main__':
    unittest.main()

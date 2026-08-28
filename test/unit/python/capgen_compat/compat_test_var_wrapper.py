"""Tests for ``capgen_compat._var_wrapper._VarWrapper``."""

import unittest

from _var_wrapper import _VarDDT, _VarWrapper


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
                 scheme_dimensions=(), used_dim_std_names=(),
                 is_constituent=False, is_constituent_arg=False):
        self.standard_name       = standard_name
        self.scheme_local_name   = scheme_local_name
        self.intent              = intent
        self.source              = source
        self.call_expr           = call_expr
        self._module_name        = module_name
        self.scheme_dimensions   = list(scheme_dimensions)
        self.used_dim_std_names  = set(used_dim_std_names)
        self.is_constituent      = is_constituent
        self.is_constituent_arg  = is_constituent_arg

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


class TestIsDdt(unittest.TestCase):
    """``write_init_files._find_and_add_host_variable`` skips a whole-DDT
    host variable but keeps a field reached *through* a DDT.  It reads
    the distinction as ``hvar.is_ddt() and not isinstance(hvar, VarDDT)``,
    the original-capgen spelling this wrapper reconstructs.
    """

    def test_intrinsic_type_is_not_ddt(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(type='real'))
        self.assertFalse(w.is_ddt())
        self.assertNotIsInstance(w, _VarDDT)

    def test_ddt_type_is_ddt(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(
            standard_name='test_list_for_ddt_argument',
            local_name='test_list', access_path='test_list',
            type='test_list_t'))
        self.assertTrue(w.is_ddt())
        # A bare whole-DDT variable is NOT a component reference, so
        # write_init_files skips it.
        self.assertNotIsInstance(w, _VarDDT)

    def test_ddt_component_is_var_ddt(self):
        w = _VarWrapper.from_host_entry(_StubHostEntry(
            standard_name='potential_temperature', local_name='theta',
            access_path='phys_state%theta', type='real'))
        self.assertIsInstance(w, _VarDDT)
        # Original capgen's VarDDT.is_ddt() reported the DDT chain, not
        # the leaf type.
        self.assertTrue(w.is_ddt())

    def test_external_type_is_ddt(self):
        """capgen's ``external:`` types have no original-capgen spelling
        and land on the DDT side: opaque, so not readable from an
        initial-conditions file."""
        w = _VarWrapper.from_host_entry(
            _StubHostEntry(type='external:some_mod:some_t'))
        self.assertTrue(w.is_ddt())

    def test_unknown_type_raises(self):
        """A suite-owned ResolvedArg carries no host entry, so no type."""
        w = _VarWrapper.from_resolved_arg(_StubResolvedArg(source='suite'))
        with self.assertRaises(ValueError):
            w.is_ddt()

    def test_resolved_arg_type_comes_from_host_entry(self):
        arg = _StubResolvedArg()
        arg.host_entry = _StubHostEntry(type='test_list_t')
        self.assertTrue(_VarWrapper.from_resolved_arg(arg).is_ddt())


class TestFromResolvedArg(unittest.TestCase):

    def test_intent_preserved(self):
        w = _VarWrapper.from_resolved_arg(_StubResolvedArg(intent='inout'))
        self.assertEqual(w.get_prop_value('intent'), 'inout')

    def test_constituent_classification(self):
        w = _VarWrapper.from_resolved_arg(
            _StubResolvedArg(standard_name='cloud_liquid_water_mixing_ratio',
                             is_constituent=True))
        self.assertTrue(w.get_prop_value('advected'))
        self.assertTrue(w.get_prop_value('constituent'))

    def test_non_constituent_is_neither(self):
        w = _VarWrapper.from_resolved_arg(_StubResolvedArg(source='host'))
        self.assertFalse(w.get_prop_value('advected'))
        self.assertFalse(w.get_prop_value('constituent'))


class TestAdvectedIsSubsetOfConstituent(unittest.TestCase):
    """``advected`` marks only what ``const_get_index(std_name)`` resolves.

    write_init_files drops advected vars from phys_var_stdnames on the
    grounds that the runtime reaches them through the constituent object.
    That holds for a base species only; a tendency lives in
    ``vars_layer_tend`` under the BASE name's index, so reporting it
    advected drops it from phys_var_stdnames and the runtime
    initialization check aborts on it.
    """

    def _flags(self, **kwargs):
        kwargs.setdefault('source', 'constituent')
        w = _VarWrapper.from_resolved_arg(_StubResolvedArg(**kwargs))
        return w.get_prop_value('advected'), w.get_prop_value('constituent')

    def test_base_constituent_is_advected(self):
        advected, constituent = self._flags(
            standard_name='cloud_liquid_water_mixing_ratio')
        self.assertTrue(advected)
        self.assertTrue(constituent)

    def test_tendency_is_constituent_but_not_advected(self):
        advected, constituent = self._flags(
            standard_name='tendency_of_cloud_liquid_water_mixing_ratio')
        self.assertFalse(advected)
        self.assertTrue(constituent)

    def test_index_var_is_not_advected(self):
        advected, constituent = self._flags(
            standard_name='index_of_cloud_liquid_water_mixing_ratio')
        self.assertFalse(advected)
        self.assertTrue(constituent)

    def test_framework_array_is_not_advected(self):
        advected, constituent = self._flags(standard_name='ccpp_constituents')
        self.assertFalse(advected)
        self.assertTrue(constituent)

    def test_register_properties_array_is_not_advected(self):
        advected, constituent = self._flags(
            standard_name='dynamic_constituents_for_my_scheme',
            is_constituent_arg=True)
        self.assertFalse(advected)
        self.assertTrue(constituent)

    def test_inferred_consumer_tendency_not_advected(self):
        # Rule (b): an unflagged intent=in consumer of a tendency still
        # resolves to source='constituent' with is_constituent False.
        advected, constituent = self._flags(
            standard_name='tendency_of_water_vapor_mixing_ratio',
            intent='in', is_constituent=False)
        self.assertFalse(advected)
        self.assertTrue(constituent)

    def test_call_string_returns_resolved_expr(self):
        w = _VarWrapper.from_resolved_arg(
            _StubResolvedArg(call_expr='gfs_statein(lb:ub, 1:nlev)'))
        self.assertEqual(w.call_string(None),
                         'gfs_statein(lb:ub, 1:nlev)')


if __name__ == '__main__':
    unittest.main()

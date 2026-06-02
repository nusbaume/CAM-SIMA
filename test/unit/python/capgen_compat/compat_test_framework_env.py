"""Tests for ``capgen_compat._framework_env.CCPPFrameworkEnv``."""

import logging
import unittest

from _framework_env import CCPPFrameworkEnv, _KNOWN_KWARGS, _KWARG_DEFAULTS


class TestCCPPFrameworkEnv(unittest.TestCase):

    def test_logger_stored_positional(self):
        log = logging.getLogger('test')
        env = CCPPFrameworkEnv(log)
        self.assertIs(env.logger, log)

    def test_known_kwargs_use_declared_defaults(self):
        env = CCPPFrameworkEnv(logging.getLogger('test'))
        for name in _KNOWN_KWARGS:
            expected = _KWARG_DEFAULTS.get(name, None)
            self.assertEqual(getattr(env, name), expected,
                             msg='kwarg {} default mismatch'.format(name))

    def test_legacy_mode_defaults_to_true(self):
        # Most CAM-SIMA scheme metadata still uses horizontal_loop_extent
        # and number_of_openmp_threads; --legacy-mode covers both at
        # parse time and is silent on metadata already migrated.
        env = CCPPFrameworkEnv(logging.getLogger('test'))
        self.assertTrue(env.legacy_mode)

    def test_legacy_mode_override_to_false(self):
        env = CCPPFrameworkEnv(logging.getLogger('test'),
                               legacy_mode=False)
        self.assertFalse(env.legacy_mode)

    def test_other_shims_default_off(self):
        # gfs_dim_aliases and legacy_auto_clone_constituents stay off
        # by default -- they have no overlap with CAM-SIMA's known
        # metadata patterns and would emit noisy banners if enabled
        # unconditionally.
        env = CCPPFrameworkEnv(logging.getLogger('test'))
        self.assertFalse(env.gfs_dim_aliases or False)
        self.assertFalse(env.legacy_auto_clone_constituents or False)

    def test_kwargs_recorded(self):
        env = CCPPFrameworkEnv(
            logging.getLogger('test'),
            host_files=['a.meta', 'b.meta'],
            scheme_files=['s.meta'],
            suites=['suite.xml'],
            host_name='my_host',
            kind_types={'kind_phys': ('iso_fortran_env', 'REAL64')},
            output_root='/tmp/out',
        )
        self.assertEqual(env.host_files, ['a.meta', 'b.meta'])
        self.assertEqual(env.host_name, 'my_host')

    def test_unknown_kwargs_accepted_silently(self):
        env = CCPPFrameworkEnv(logging.getLogger('test'),
                               some_future_option='yes')
        self.assertEqual(env.some_future_option, 'yes')


if __name__ == '__main__':
    unittest.main()

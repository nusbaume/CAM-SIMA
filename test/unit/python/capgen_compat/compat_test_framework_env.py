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

    def test_legacy_auto_clone_constituents_defaults_to_true(self):
        # CAM-SIMA's atmospheric_physics tree relies on
        # original-capgen's auto-clone-static-constituent path: ~16
        # schemes declare advected=True on _run args and let the
        # framework register the constituent on their behalf.  Without
        # the shim capgen-ng rejects them.  Single-instance only;
        # capgen-ng's runner aborts before parsing if the host opts
        # into multi-instance, so the default is safe for any
        # single-instance CAM-SIMA build.
        env = CCPPFrameworkEnv(logging.getLogger('test'))
        self.assertTrue(env.legacy_auto_clone_constituents)

    def test_other_shims_default_off(self):
        # gfs_dim_aliases stays off by default -- it targets GFS
        # radiation/composition vertical-dim spellings that CAM-SIMA
        # metadata doesn't use.
        env = CCPPFrameworkEnv(logging.getLogger('test'))
        self.assertFalse(env.gfs_dim_aliases or False)

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

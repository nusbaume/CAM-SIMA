# capgen_compat — CAM-SIMA compatibility layer for capgen-ng

This directory lets CAM-SIMA's existing `cime_config/cam_autogen.py`,
`src/data/generate_registry_data.py`, and `src/data/write_init_files.py`
keep their original-capgen import surface (`from ccpp_capgen import
capgen`, `from parse_tools import ...`, `from fortran_tools import
FortranWriter`, etc.) while the underlying CCPP code generator is the
new capgen-ng.

CAM-SIMA owns this directory.  Capgen-ng owns nothing in here.
Capgen-ng's only public surface this layer consumes is:

* `ccpp_capgen_ng.capgen(..., return_state=True)` — returns
  `(host_dict, suite_resolutions)` so the adapter can build its
  `cap_database` facade without re-running load + resolve.
* The three types whose field names are read by the adapter:
  `HostVarEntry`, `ResolvedArg`, `SuiteResolution`.

Renaming or removing any field on those three classes will break the
adapter; the compat tests under `test/unit/python/capgen_compat/`
catch that condition in CI.

## Layout

```
cime_config/capgen_compat/
├── README.md
├── __init__.py
├── ccpp_capgen.py            # flat shim — re-exports `capgen` + `CapDatabase`
├── framework_env.py          # flat shim — re-exports `CCPPFrameworkEnv`
├── ccpp_state_machine.py     # flat shim — re-exports `CCPP_STATE_MACH`
├── parse_tools.py            # flat shim — re-exports capgen-ng's parse_tools + supplements
├── metadata_table.py         # flat shim — re-exports parse_metadata_file + synthesises find_scheme_names
├── fortran_tools.py          # flat shim — re-exports FortranWriter
├── fortran_write.py          # vendored from original ccpp_framework/scripts/fortran_tools/
├── _runner.py                # capgen(run_env, return_db=True) entry point
├── _cap_database.py          # CapDatabase + _HostDict + _CallList
├── _var_wrapper.py           # _VarWrapper + _Source (14-method surface)
├── _framework_env.py         # CCPPFrameworkEnv implementation
└── _state_machine.py         # CCPP_STATE_MACH implementation
```

The leading-underscore files hold the implementations; the bare-name
files at the top are flat module shims so the legacy
`from <name> import ...` style works once this directory is on
`sys.path`.

## How `sys.path` is wired

`cam_autogen.py` (and the unit tests) prepend
`cime_config/capgen_compat/` to `sys.path` before any `from
ccpp_capgen import ...` import.  That makes the flat shim files
(`ccpp_capgen.py`, `parse_tools.py`, ...) resolve here rather than in
the pinned `ccpp_framework/scripts/` external.

`capgen_compat/` itself relies on capgen-ng being importable; the
pinned `ccpp_framework/capgen-ng/` external must also be on
`sys.path` so the adapter can import `metadata.parse_tools`,
`metadata.metadata_table`, etc.  `cam_autogen.py` adds both.

## Removal procedure

When CAM-SIMA's `write_init_files.py` is ported to consume
capgen-ng's native API (or `datatable.xml` directly), retire this
directory:

```
rm -rf cime_config/capgen_compat
rm -rf test/unit/python/capgen_compat
# Revert the sys.path additions in cam_autogen.py + test scripts
grep -rn 'capgen_compat' .   # should be empty
```

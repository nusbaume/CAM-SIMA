# capgen_compat — CAM-SIMA compatibility layer for capgen-ng

This directory is **transient scaffolding**.  It lets CAM-SIMA's
existing autogen pipeline (`cime_config/cam_autogen.py`,
`src/data/generate_registry_data.py`, `src/data/write_init_files.py`,
`cime_config/hist_config.py`) keep working unchanged while the
underlying CCPP code generator transitions from original ccpp_capgen
to capgen-ng.  The end-state is an empty directory; every file here
retires as CAM-SIMA migrates its consumers to the agreed convergence
interface (next section).

CAM-SIMA owns this directory.  Capgen-ng owns nothing in here.

## Interface convergence goal

The long-term goal is that CAM-SIMA interacts with capgen-ng
through **one** of two interfaces (in order of preference):

1. **Command-line invocation** of three utilities:
   - `ccpp_validator.py` — returns success or failure with meaningful
     error messages.
   - `ccpp_capgen_ng.py` — returns success or failure only.  Generated
     output is on disk (group caps, suite caps, host cap,
     `datatable.xml`, etc.).
   - `ccpp_datafile.py` — returns whatever it is asked to return
     (file lists, dependency lists, suite metadata, etc.).

2. **Python API**, if and only if CLI invocation is impossible from
   CAM-SIMA's context.  The Python API **must be option-equivalent**
   to the three CLI utilities — same option names, same semantics, same
   return contracts:
   - The option *expression* can differ (CLI `--host-files
     a.meta,b.meta`; Python `host_files=['a.meta', 'b.meta']`), but
     the *option set* and the *return contract* are identical.
   - No Python entry point exposes data structures that the
     corresponding CLI utility doesn't surface through its outputs.
     If CAM-SIMA needs a piece of information from a Python call, the
     CLI must already expose it through `datatable.xml` (or another
     on-disk artifact).

Anything beyond these two interfaces is a violation of the
convergence goal.  In particular: capgen-ng's current
`return_state=True` kwarg (which hands back
`(host_dict, suite_resolutions)` — internal Python objects with no
CLI equivalent) is **scaffolding for this compat layer only** and
retires with the compat layer.  No production CAM-SIMA code path
should ever call it.

## Capgen-ng surface this layer consumes (scaffolding inventory)

These are the touchpoints that violate the convergence goal today.
Each retires by the end of the phased plan below.

| Surface | Used by | Retires when |
|---|---|---|
| `ccpp_capgen_ng.capgen(..., return_state=True)` returning `(host_dict, suite_resolutions)` | `_runner.capgen()` | Phase B (`write_init_files` migrates to `datatable.xml`) |
| Field names on `HostVarEntry`, `ResolvedArg`, `SuiteResolution` (read by `_var_wrapper.py` and `_cap_database.py`) | The CapDatabase adapter | Phase B |
| Direct attribute access on `MetaVar` / `MetadataSection` (read by `generate_registry_data.py` via monkey-patched methods) | `metadata_table.py` monkey-patches | Phase C |
| `metadata.metadata_table.parse_metadata_file` + `_parse_lines` (called by the parse-time rewriter) | `metadata_table.py` | Phase F |

## File inventory (~2570 LOC total)

### Flat-module shims (~170 LOC)

Re-export capgen-ng symbols at the flat module paths CAM-SIMA imports
from today (`from ccpp_capgen import ...`, `from parse_tools import
...`, etc.).  Each retires the day CAM-SIMA updates the matching
imports to capgen-ng's native paths — or, in the end-state, drops
the import entirely in favour of CLI invocation.

| File | Re-exports |
|---|---|
| `ccpp_capgen.py` | `capgen`, `CapDatabase` |
| `framework_env.py` | `CCPPFrameworkEnv` |
| `ccpp_state_machine.py` | `CCPP_STATE_MACH` |
| `parse_tools.py` | capgen-ng's `metadata.parse_tools` symbols + `ParseObject` |
| `metadata_table.py` | `parse_metadata_file`, `find_scheme_names`, `MetadataTable` (with monkey-patches — see below) |
| `fortran_tools.py` | `FortranWriter` |
| `var_props.py` | `is_horizontal_dimension`, `is_vertical_dimension`, the two dim-name lists |

### CapDatabase adapter (~850 LOC)

The actual capgen-ng → original-capgen Python-surface translation.
Reads `HostVarEntry` / `ResolvedArg` / `SuiteResolution` and exposes
them as the `cap_database` API that `write_init_files.py` consumes.
**Every line here violates the convergence goal** (it depends on
capgen-ng's internal Python state).

| File | Role |
|---|---|
| `_runner.py` | `capgen(run_env, return_db=True)` entry point — wraps `ccpp_capgen_ng.capgen` with `return_state=True` |
| `_cap_database.py` | `CapDatabase` + `_HostDict` + `_CallList` |
| `_var_wrapper.py` | `_VarWrapper` + `_Source` — the 14-method per-variable surface |
| `_framework_env.py` | `CCPPFrameworkEnv` config-object stub |
| `_state_machine.py` | `CCPP_STATE_MACH` with the canonical phase list |

### Parse-time rewrites + monkey-patches (~530 LOC in `metadata_table.py`)

Capgen-ng's parser is stricter and reads metadata into different
data classes than original capgen.  The shim closes the gap at
parse time so CAM-SIMA's metadata-as-Python-objects code paths keep
working:

* `_rewrite_module_to_host` — rewrites `type = module` →
  `type = host` in-memory (capgen-ng rejects the legacy spelling),
  records the affected table names in `MODULE_ORIGIN_TABLE_NAMES`
  so `_VarWrapper` can route module-allocated vars through
  `ptype = 'module'` (the classification `write_init_files.py`'s
  filter requires).
* `_DROP_ATTRS` — strips per-variable attributes capgen-ng doesn't
  model (currently `persistence`, used by CAM-SIMA's allocator
  cadence hint; semantically irrelevant to cap generation).
* `_backfill_module_name` — defaults each `MetadataTable.module_name`
  to its `table_name` when no explicit override was declared,
  mirroring original capgen's implicit fallback.
* Monkey-patches: `MetaVar.get_prop_value` plus six methods
  (`get_dimensions`, `has_horizontal_dimension`,
  `has_vertical_dimension`, `array_ref`, `intrinsic_elements`,
  `call_string`) and `MetadataSection.variable_list(std_vars=...,
  loop_vars=..., consts=...)`.  Together these surface raw
  capgen-ng `MetaVar` / `MetadataSection` instances under
  original-capgen's accessor API, so CAM-SIMA's direct
  `for var in section.variables` iteration paths in
  `generate_registry_data.py` keep working.
* `find_scheme_names` — lightweight string scan (does not go through
  capgen-ng's strict parser, so namelist-reader pseudo-schemes are
  enumerable for `_find_metadata_files`).

### Vendored utilities (~1010 LOC)

Verbatim copies of original-capgen utility classes that CAM-SIMA's
own scripts call into directly (NOT because capgen-ng requires
them — capgen-ng has no use for any of them).  These exist
because:

* `hist_config.py` uses `ParseObject` to parse namelist-style
  history configs.
* `write_init_files.py` and `generate_registry_data.py` use
  `FortranWriter` to emit Fortran with managed indentation and
  line wrapping.
* `parse_object.py` inherits from a richer `ParseContext` than
  capgen-ng exposes (writable `line_num`, region stack, etc.); the
  vendored `parse_source.py` carries that fuller `ParseContext` plus
  `ContextRegion` / `ParseContextError` / `ParseSource`.

| File | What it carries |
|---|---|
| `parse_source.py` (409 LOC) | Original-capgen-style `ParseContext` (writable, with region stack); `ContextRegion`; `ParseContextError`; `ParseSource`; `context_string` and a few utility helpers.  `CCPPError` / `ParseSyntaxError` / `ParseInternalError` are re-exported from capgen-ng (not vendored) so the exception identity is shared. |
| `parse_object.py` (176 LOC) | `ParseObject` — line-buffered free-form config parser, backslash continuation. |
| `fortran_write.py` (436 LOC) | `FortranWriter` — managed Fortran output with indentation, 132-column wrapping, comment formatting. |

These look stable but are not "permanent infrastructure" — they
are scaffolding tied to CAM-SIMA's pre-migration code paths.  Each
retires when its consumer is rewritten.

## How `sys.path` is wired

`cam_autogen.py` (and the unit tests) prepend
`cime_config/capgen_compat/` to `sys.path` before any
`from ccpp_capgen import ...`-style import.  That makes the flat
shims (`ccpp_capgen.py`, `parse_tools.py`, ...) resolve here.

`capgen_compat/` itself relies on capgen-ng being importable, so the
pinned `ccpp_framework/capgen-ng/` external is also appended to
`sys.path`.  `cam_autogen.py` adds both.

## Phased retirement plan

End-state: this directory does not exist.  CAM-SIMA's autogen
pipeline interacts with capgen-ng only through the three CLI
utilities (or, if CLI is impossible from CAM-SIMA's context, a
Python API that is **option-equivalent** to them).

Each phase has a measurable LOC drop and a clearly-scoped CAM-SIMA
deliverable.  They can land in any order, though the suggested order
below minimises churn.

| Phase | What CAM-SIMA does | What retires |
|---|---|---|
| **A** | Discover schemes via `ccpp_datafile.py --schemes datatable.xml` (CLI) instead of walking `.meta` files | `find_scheme_names` (~50 LOC of `metadata_table.py`) |
| **B** | Rewrite `write_init_files.py` to consume `datatable.xml` only (no `cap_database` Python object).  Drop `FortranWriter` in the rewrite — use direct f-strings or a small in-tree emitter. | `_cap_database.py`, `_var_wrapper.py`, `_runner.py`, the `MetaVar` / `MetadataSection` monkey-patches, **`fortran_write.py`** if it was the last `FortranWriter` caller, and the `return_state=True` hook on `ccpp_capgen_ng.capgen` (delete on the capgen-ng side) |
| **C** | Rewrite `generate_registry_data.py` to use capgen-ng's CLI + a small Fortran emitter | rest of `metadata_table.py`'s parse-shim, **and `fortran_write.py`** if it had not already gone |
| **D** | Rewrite `hist_config.py` (or its dependents) to use a stdlib / native config parser instead of `ParseObject` | `parse_object.py`, **`parse_source.py`** (no remaining importer), `parse_tools.py` shim |
| **E** | Mechanical sweep: replace `from ccpp_capgen import …` / `from framework_env import …` / etc. with capgen-ng's native paths, or remove them entirely if the CLI replaces them | Remaining flat-module shims |
| **F** | Migrate on-disk metadata (`type = module` → `type = host`; drop `persistence = …`); migrate registry XML (`<file type="module">` → `<file type="host">`) | The parse-time rewriter dies (`_rewrite_module_to_host`, `_DROP_ATTRS`, `_backfill_module_name`) |
| **G** | `rm -rf cime_config/capgen_compat/` + revert `sys.path` additions in `cam_autogen.py` + test scripts | Directory gone |

## Asks of capgen-ng

These keep the convergence-goal contract intact.  No asks for
"expose more Python objects" — that would entrench the wrong
interface.

1. **Delete the `return_state=True` kwarg** on
   `ccpp_capgen_ng.capgen` once Phase B lands.  No production caller
   should ever depend on it.
2. **If CAM-SIMA cannot avoid Python imports**, capgen-ng exposes
   a Python wrapper for each of the three CLI utilities — `capgen()`,
   `validator()`, `datafile()` — taking the same option names as
   keyword arguments and returning the same contract
   (success/failure with `errmsg`; for datafile, the requested
   value).  Internally these wrappers do exactly what the CLI does.
   No additional Python-only surface.
3. **Stable on-disk artifacts.**  `datatable.xml` is the
   non-negotiable cross-language contract.  Adding fields to it is
   backward-compatible; renaming or removing fields is not.

## Removal procedure (once Phases A–F land)

```
rm -rf cime_config/capgen_compat
rm -rf test/unit/python/capgen_compat
# Revert the sys.path additions in cam_autogen.py + test scripts
grep -rn 'capgen_compat' .   # should be empty
```

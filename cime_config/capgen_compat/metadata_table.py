"""Flat-module shim for original capgen's ``metadata_table``.

Re-exports a CAM-SIMA-shaped ``parse_metadata_file`` on top of
capgen-ng's :func:`metadata.metadata_table.parse_metadata_file`.

Signature adaptation
--------------------
Original capgen's signature::

    parse_metadata_file(filename, known_ddts, run_env,
                        skip_ddt_check=False,
                        relative_source_path=False)

Capgen-ng's signature::

    parse_metadata_file(file_path: str) -> List[MetadataTable]

The extra arguments served original-capgen-internal purposes
(cross-referencing DDT lookups against a pre-built ``known_ddts``
list, threading the ``CCPPFrameworkEnv`` through for logger access,
selecting between absolute and relative source-path resolution).
Capgen-ng's parser does not need any of them -- DDT cross-references
are built lazily, logging is via the module-level logger, and source
paths are always absolute.  The shim accepts all five positional /
keyword arguments and silently discards the extras.

``find_scheme_names`` is synthesised on top of capgen-ng's
:func:`parse_metadata_file` plus a ``t.is_scheme`` filter; original
capgen exported it directly.
"""

from metadata.metadata_table import (
    parse_metadata_file as _capgen_ng_parse_metadata_file,
    MetadataTable,  # noqa: F401
    MetadataSection,
    MetaVar,
    _parse_lines as _capgen_ng_parse_lines,
)


# Map original-capgen ``Var.get_prop_value`` property names to the
# matching capgen-ng ``MetaVar`` attribute.  Original capgen's
# property surface is broader than what CAM-SIMA exercises through
# direct ``MetaVar`` iteration today; we cover the names that appear
# in ``generate_registry_data.py`` / ``write_init_files.py`` plus the
# obvious neighbours (``intent`` / ``optional`` for completeness even
# though host metadata typically doesn't carry them).  A miss returns
# ``None`` -- matches original capgen's behaviour for unknown props.
_METAVAR_PROP_MAP = {
    'standard_name':  'standard_name',
    'local_name':     'local_name',
    'long_name':      'long_name',
    'units':          'units',
    'dimensions':     'dimensions',
    'type':           'type',
    'kind':           'kind',
    'intent':         'intent',
    'optional':       'optional',
    'protected':      'protected',
    'allocatable':    'allocatable',
    'active':         'active',
    'advected':       'advected',
    'constituent':    'constituent',
    'molar_mass':     'molar_mass',
    'top_at_one':     'top_at_one',
    'diagnostic_name_fixed': 'diagnostic_name_fixed',
}


def _metavar_get_prop_value(self, prop_name):
    """Original-capgen-style ``Var.get_prop_value`` on ``MetaVar``.

    Returns the matching capgen-ng attribute, or ``None`` for unknown
    property names (matches original capgen's lenient policy).
    Monkey-patched onto :class:`MetaVar` at import time so existing
    instances pick it up automatically.
    """
    attr = _METAVAR_PROP_MAP.get(prop_name)
    if attr is None:
        return None
    return getattr(self, attr, None)


if not hasattr(MetaVar, 'get_prop_value'):
    MetaVar.get_prop_value = _metavar_get_prop_value


# ----------------------------------------------------------------------
# Additional original-capgen-style methods on MetaVar.
#
# CAM-SIMA's ``generate_registry_data.py`` and ``write_init_files.py``
# iterate ``MetadataSection.variables`` directly and call original
# capgen's per-Var methods on each entry.  ``_VarWrapper`` covers the
# same surface for the wrapped CapDatabase path; here we monkey-patch
# the bare ``MetaVar`` class so the raw-iteration path works too.
# ----------------------------------------------------------------------

import re as _re

_HORIZ_DIM_STDS = frozenset({
    'horizontal_dimension',
    'horizontal_loop_extent',
})
_VERT_DIM_STDS = frozenset({
    'vertical_layer_dimension',
    'vertical_interface_dimension',
})
_ARRAY_REF_RE = _re.compile(r'^(\w+)\s*\(([^)]+)\)\s*$')


def _strip_bounds(dim):
    """Strip a ``lower:upper`` bound spec to the upper-bound name."""
    if ':' in dim:
        return dim.split(':', 1)[1].strip()
    return dim.strip()


def _metavar_get_dimensions(self):
    """Return a copy of the dimension standard-name list."""
    return list(self.dimensions)


def _metavar_has_horizontal_dimension(self):
    """True iff any declared dim is a horizontal standard name."""
    return any(_strip_bounds(d) in _HORIZ_DIM_STDS for d in self.dimensions)


def _metavar_has_vertical_dimension(self):
    """Return the vertical dim's standard name, or ``''``.

    Original capgen's predicate is truthy when a vertical dim is
    present and returns the name itself so the caller can use it
    directly.
    """
    for d in self.dimensions:
        stripped = _strip_bounds(d)
        if stripped in _VERT_DIM_STDS:
            return stripped
    return ''


def _metavar_array_ref(self):
    """Return a regex match for a sliced ``local_name``, or ``None``.

    Usage from write_init_files:

        aref = hvar.array_ref()
        if aref:
            dimlist = [x.strip() for x in aref.group(2).split(',')]
    """
    return _ARRAY_REF_RE.match(self.local_name)


def _metavar_intrinsic_elements(self):
    """Sub-element standard names for array-of-DDT entries.

    Returns ``None`` (not ``[]``) for plain vars; CAM-SIMA's
    ``write_init_files.py`` distinguishes via
    ``isinstance(ielem, list)``.  Capgen-ng does not currently expose
    array-of-DDT decomposition on bare MetaVar; the only path that
    needs it goes through CapDatabase's host_dict facade
    (which delegates to ``_VarWrapper.intrinsic_elements``).
    """
    return None


def _metavar_call_string(self, host_dict=None):
    """Return the Fortran expression for use at a call site.

    Bare ``MetaVar`` from ``MetadataSection.variables`` carries no
    pre-baked call expression -- the raw ``local_name`` is the right
    answer for the registry-generated metadata path (vars are
    module-level decls; the call site is just the local name).
    """
    return self.local_name


_METAVAR_ADDED_METHODS = {
    'get_dimensions':           _metavar_get_dimensions,
    'has_horizontal_dimension': _metavar_has_horizontal_dimension,
    'has_vertical_dimension':   _metavar_has_vertical_dimension,
    'array_ref':                _metavar_array_ref,
    'intrinsic_elements':       _metavar_intrinsic_elements,
    'call_string':              _metavar_call_string,
}

for _name, _fn in _METAVAR_ADDED_METHODS.items():
    if not hasattr(MetaVar, _name):
        setattr(MetaVar, _name, _fn)


# Original capgen's standard names that get classified as "loop
# variables" -- they're horizontal-bound / vertical-index axes the
# host injects per chunk.  generate_registry_data.py filters them out
# of the per-section variable list to avoid double-declaring them in
# generated host data structures.
_CCPP_LOOP_VAR_STDNAMES = frozenset({
    'horizontal_loop_extent',
    'horizontal_loop_begin',
    'horizontal_loop_end',
    'vertical_layer_index',
    'vertical_interface_index',
})


# Original capgen's "constant variables" set is the framework-supplied
# universally-available constants -- the only entry is
# ``ccpp_constant_one``.  Note this is NOT the same as the
# ``protected = True`` attribute: ``protected`` flags vars whose
# storage the host has marked read-only; ``CCPP_CONSTANT_VARS`` flags
# framework-supplied numeric constants.  The category filter in
# ``variable_list`` uses the latter, not the former.
_CCPP_CONSTANT_VAR_STDNAMES = frozenset({
    'ccpp_constant_one',
})


def _variable_list(self, recursive=False,
                   std_vars=True, loop_vars=True, consts=True):
    """Original-capgen-compat ``MetadataSection.variable_list`` method.

    capgen-ng's :class:`metadata.metadata_table.MetadataSection`
    exposes a bare ``variables`` list attribute; CAM-SIMA's
    ``generate_registry_data.py`` (and downstream code) call
    ``mheader.variable_list(loop_vars=False, consts=False)`` to filter
    by variable category.  The category rules mirror original capgen's
    ``include_var_in_list`` predicate:

    * ``std_vars`` -- regular vars (not loop vars, not constants).
    * ``loop_vars`` -- the five fixed loop-bound / vertical-index
      standard names listed in :data:`_CCPP_LOOP_VAR_STDNAMES`.
    * ``consts`` -- framework-constant standard names listed in
      :data:`_CCPP_CONSTANT_VAR_STDNAMES` (just ``ccpp_constant_one``).
      Note: NOT the ``protected = True`` attribute; that's a separate
      storage flag.

    *recursive* is accepted for signature parity and ignored --
    capgen-ng's MetadataSection has no parent-dict concept and the
    only CAM-SIMA call site sets ``recursive=False``.

    Monkey-patched onto :class:`MetadataSection` at import time so
    existing capgen-ng MetadataSection instances pick it up
    automatically.
    """
    out = []
    for var in self.variables:
        stdname = var.standard_name
        is_loop = stdname in _CCPP_LOOP_VAR_STDNAMES
        is_const = stdname in _CCPP_CONSTANT_VAR_STDNAMES
        if is_loop:
            keep = loop_vars
        elif is_const:
            keep = consts
        else:
            keep = std_vars
        if keep:
            out.append(var)
    return out


# Install once per Python process.  Idempotent: skipped if already
# present (e.g. during repeated test runs in the same interpreter).
if not hasattr(MetadataSection, 'variable_list'):
    MetadataSection.variable_list = _variable_list


import os as _os
import re as _re_parse
import tempfile as _tempfile


_TABLE_TYPE_RE = _re_parse.compile(
    r'^(?P<indent>\s*)type(?P<sep>\s*=\s*)module\b(?P<rest>.*)$'
)
_TABLE_NAME_RE = _re_parse.compile(r'^\s*name\s*=\s*(\S+)\s*$')
_TABLE_HDR     = '[ccpp-table-properties]'

# Attributes capgen-ng does not recognise but original capgen did.
# Listed here for parse-time stripping by ``_rewrite_module_to_host``.
# Each is semantically irrelevant to cap generation (capgen-ng's
# resolver ignores all of them); the consumer is CAM-SIMA's own
# tooling, which reads metadata through THIS shim and so never sees
# the attribute either way.  Lines matching ``<indent><name>=...``
# are silently dropped.
#
# * ``persistence = timestep|run`` -- CAM-SIMA's allocator reset
#   cadence hint.  No capgen-ng equivalent.
_DROP_ATTRS = frozenset({
    'persistence',
})

_DROP_ATTR_RE = _re_parse.compile(
    r'^\s*(' + '|'.join(_DROP_ATTRS) + r')\s*=', _re_parse.IGNORECASE
)


# Module-level set of table names whose source metadata carried the
# original-capgen ``type = module`` spelling.  ``_var_wrapper`` reads
# this to classify the source variables as ``ptype = 'module'``
# (matches original capgen's behaviour) rather than the default
# ``ptype = 'host'``.  Populated incrementally by every call to
# :func:`parse_metadata_file` (and by the pre-scan in
# ``_runner.capgen``).
MODULE_ORIGIN_TABLE_NAMES = set()


def _rewrite_module_to_host(text):
    """Rewrite ``type = module`` to ``type = host`` in *text*.

    Returns ``(rewritten_text, table_names_that_were_module)`` where
    ``table_names_that_were_module`` is the set of table names whose
    ``[ccpp-table-properties]`` block declared ``type = module``.
    Both occurrences in a block (the table-properties one and the
    matching arg-table one) are rewritten; the table-properties
    occurrence is the one that drives the table-name capture.

    capgen-ng's parser rejects ``type = module`` outright; the rewrite
    keeps the metadata semantically valid for capgen-ng while
    preserving the original-capgen distinction in
    ``MODULE_ORIGIN_TABLE_NAMES`` so ``_VarWrapper.from_host_entry``
    can route module-allocated vars through ``ptype = 'module'``.
    """
    out_lines = []
    flagged = set()
    cur_table = None
    in_table_props = False
    saw_module = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == _TABLE_HDR:
            # Flush the previous block's accounting.
            if saw_module and cur_table is not None:
                flagged.add(cur_table.lower())
            cur_table = None
            in_table_props = True
            saw_module = False
            out_lines.append(line)
            continue
        if stripped.startswith('[') and stripped.endswith(']'):
            # Any other section header closes the table-properties block.
            in_table_props = False
        if in_table_props:
            m = _TABLE_NAME_RE.match(line)
            if m:
                cur_table = m.group(1)
        # Drop attributes capgen-ng doesn't model (see ``_DROP_ATTRS``).
        # They live inside per-variable [ name ] blocks and capgen-ng
        # rejects unknown attribute names; silently skipping them
        # keeps the metadata semantically valid for capgen-ng while
        # preserving the original file on disk unchanged.
        if _DROP_ATTR_RE.match(line):
            continue
        # Rewrite the ``type = module`` line wherever it appears
        # (table-properties block and the paired arg-table block).
        m = _TABLE_TYPE_RE.match(line)
        if m:
            saw_module = True
            line = '{indent}type{sep}host{rest}'.format(
                indent=m.group('indent'),
                sep=m.group('sep'),
                rest=m.group('rest'),
            )
            if not line.endswith('\n'):
                line += '\n'
        out_lines.append(line)
    # End-of-file flush.
    if saw_module and cur_table is not None:
        flagged.add(cur_table.lower())
    return ''.join(out_lines), flagged


def _backfill_module_name(tables):
    """Default each table's empty ``module_name`` to its ``table_name``.

    Original capgen exposed ``MetadataTable.module_name`` as the
    Fortran module exporting the table's symbols, and treated the
    table name as the implicit default when no ``module_name = ...``
    override was declared.  Capgen-ng leaves the attribute as ``''``
    in that case and resolves the fallback elsewhere (deeper in the
    cap emitter).  CAM-SIMA's ``generate_registry_data.py`` reads
    ``mtable.module_name`` directly when building its
    ``var_module_dict`` -- an empty string there produces broken
    ``use , only: ...`` lines in the generated Fortran.  Mirror
    original capgen's default at the parse-shim layer instead of
    teaching cam-sima to apply the fallback itself.
    """
    for t in tables:
        if not t.module_name:
            t.module_name = t.table_name
    return tables


def parse_metadata_file(filename, known_ddts=None, run_env=None,
                        skip_ddt_check=False,
                        relative_source_path=False):
    """Original-capgen-shaped ``parse_metadata_file`` wrapper.

    Forwards *filename* to capgen-ng's parser and silently discards
    every other argument; capgen-ng's parser does not need them.

    If *filename* declares any ``type = module`` tables, the contents
    are rewritten in-memory to ``type = host`` (so capgen-ng's parser
    accepts the file) and the affected table names are added to
    :data:`MODULE_ORIGIN_TABLE_NAMES`.  The rewrite is invisible to
    callers; the returned tables look exactly like capgen-ng would
    have produced for a natively-``type = host`` file.

    Each returned table also has its ``module_name`` defaulted to
    ``table_name`` if no explicit override was declared (matching
    original capgen's semantics; see :func:`_backfill_module_name`).
    """
    try:
        with open(filename, encoding='utf-8') as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        # Let capgen-ng surface the real error.
        return _backfill_module_name(_capgen_ng_parse_metadata_file(filename))

    rewritten, flagged = _rewrite_module_to_host(text)
    MODULE_ORIGIN_TABLE_NAMES.update(flagged)

    if rewritten == text:
        # Nothing was rewritten and no attrs were dropped.
        return _backfill_module_name(_capgen_ng_parse_metadata_file(filename))

    # Hand the rewritten content to capgen-ng's ``_parse_lines``
    # directly with the ORIGINAL filename as the source location.
    # That keeps error messages, line-number references, and
    # per-table ``source_path`` resolution pointing at the real file
    # (no temp-file leakage into user-visible diagnostics) while
    # capgen-ng's parser sees the rewritten contents.
    rewritten_lines = rewritten.splitlines(keepends=True)
    return _backfill_module_name(
        _capgen_ng_parse_lines(rewritten_lines, filename))


# Monkey-patch capgen-ng's own ``parse_metadata_file`` so its
# internal calls (made from ``ccpp_capgen_ng.capgen``,
# ``_load_metadata_files``, etc.) route through our rewriter and
# pick up the type=module → type=host fix-up.  The shim's public
# ``parse_metadata_file`` above also uses the same rewriter -- this
# patch covers the path cam-sima doesn't control.
import metadata.metadata_table as _capgen_ng_meta_mod  # noqa: E402

if getattr(_capgen_ng_meta_mod.parse_metadata_file,
           '_capgen_compat_wrapped', False) is False:
    _orig = _capgen_ng_parse_metadata_file

    def _patched_parse_metadata_file(file_path):
        return parse_metadata_file(file_path)

    _patched_parse_metadata_file._capgen_compat_wrapped = True
    _capgen_ng_meta_mod.parse_metadata_file = _patched_parse_metadata_file


def _scan_module_origin_tables(file_path):
    """Return the set of table names in *file_path* whose
    ``[ccpp-table-properties]`` declared ``type = module``.

    Used by ``_runner.capgen`` to pre-populate
    :data:`MODULE_ORIGIN_TABLE_NAMES` before capgen-ng's internal
    metadata parser runs (capgen-ng's parser calls
    :func:`metadata.metadata_table.parse_metadata_file` directly --
    not through this shim -- so the pre-scan ensures the set is up to
    date by the time ``_VarWrapper.from_host_entry`` is invoked).
    """
    try:
        with open(file_path, encoding='utf-8') as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return set()
    _, flagged = _rewrite_module_to_host(text)
    return flagged


def find_scheme_names(file_path: str) -> list:
    """Return the list of scheme names declared in ``file_path``.

    Lightweight string scan: walk ``[ccpp-table-properties]`` blocks
    and collect the ``name = ...`` field of every block whose
    ``type = scheme``.  Original capgen exported this helper as a
    similarly lightweight scan; CAM-SIMA's ``cam_autogen.py`` uses it
    as a discovery callback into ``_find_metadata_files`` -- it cares
    only about scheme NAMES, not whether each scheme block is a
    valid CCPP scheme by capgen-ng's strict semantic rules (which
    includes per-phase arg-table validation).  Routing through
    :func:`parse_metadata_file` would fail-fast on degenerate
    discovery fixtures (e.g. namelist-reader pseudo-schemes whose
    arg-table section names don't carry a ``_<phase>`` suffix); the
    string scan side-steps that check.
    """
    names = []
    try:
        with open(file_path, encoding='utf-8') as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return names
    cur_name = None
    cur_type = None
    in_table_props = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == _TABLE_HDR:
            if (cur_type or '').lower() == 'scheme' and cur_name:
                names.append(cur_name)
            cur_name = None
            cur_type = None
            in_table_props = True
            continue
        if stripped.startswith('[') and stripped.endswith(']'):
            in_table_props = False
            continue
        if not in_table_props:
            continue
        m = _TABLE_NAME_RE.match(line)
        if m:
            cur_name = m.group(1)
            continue
        m = _re_parse.match(r'^\s*type\s*=\s*(\S+)\s*$', line)
        if m:
            cur_type = m.group(1)
    # End-of-file flush.
    if (cur_type or '').lower() == 'scheme' and cur_name:
        names.append(cur_name)
    return names


__all__ = [
    'parse_metadata_file',
    'MetadataTable',
    'find_scheme_names',
]

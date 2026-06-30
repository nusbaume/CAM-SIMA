"""Flat-module shim for original capgen's ``parse_tools``.

Re-exports symbols from capgen's ``metadata.parse_tools`` package
and supplements with two helpers that live in the xml_tools submodule
but aren't re-exported at the package level
(``validate_xml_file``, ``find_schema_file``).

``ParseObject`` is original capgen's free-form-config parser state
container.  capgen does not bundle one; the compat layer ships a
verbatim vendor copy at ``capgen_compat/parse_object.py`` (~166 LOC,
no external deps beyond ``parse_source``) so CAM-SIMA's
``hist_config.py`` namelist parser keeps working.
"""

from metadata.parse_tools import (
    CCPPError,
    ParseSyntaxError,
    ParseInternalError,
    ParseContext,
    context_string,
    init_log,
    set_log_level,
    set_log_to_null,
    set_log_to_stdout,
    read_xml_file,
    find_schema_version,
    expand_nested_suites,
    write_xml_file,
    write_if_changed,
    open_if_changed,
)

from metadata.parse_tools.xml_tools import (
    validate_xml_file,
    find_schema_file,
)

# Vendored ParseObject -- see ``capgen_compat/parse_object.py``.
from parse_object import ParseObject


__all__ = [
    'CCPPError',
    'ParseSyntaxError',
    'ParseInternalError',
    'ParseContext',
    'ParseObject',
    'context_string',
    'init_log',
    'set_log_level',
    'set_log_to_null',
    'set_log_to_stdout',
    'read_xml_file',
    'find_schema_version',
    'find_schema_file',
    'validate_xml_file',
    'expand_nested_suites',
    'write_xml_file',
    'write_if_changed',
    'open_if_changed',
]

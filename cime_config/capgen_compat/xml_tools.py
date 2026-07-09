"""Vendored general-purpose XML validation helpers for the compat layer.

capgen's ``ccpp_capgen`` pipeline only ever validates *suite* SDF files, so
capgen's own ``validate_xml_file`` was trimmed to suite-only.  CAM-SIMA's
``cime_config`` tools need the more general validator: ``create_readnl_files``
passes an explicit schema *file* path, and ``generate_registry_data`` validates
against a ``registry`` schema root.  Those needs are owned here in the compat
layer rather than reaching into a capgen internal.

``CCPPError`` is re-exported from capgen (via the local ``parse_source`` shim)
so a validation error raised here is the same class CAM-SIMA catches.
"""

import os
import shutil
import subprocess

from parse_source import CCPPError


def find_schema_file(schema_root, version, schema_path=None):
    """Return ``<schema_root>_v<major>_<minor>.xsd`` under *schema_path*
    (or the current directory), or ``None`` if no such file exists."""
    verstring = '_'.join([str(x) for x in version])
    schema_filename = "{}_v{}.xsd".format(schema_root, verstring)
    if schema_path:
        schema_file = os.path.join(schema_path, schema_filename)
    else:
        schema_file = schema_filename
    if os.path.exists(schema_file):
        return schema_file
    return None


def validate_xml_file(filename, schema_root, version, logger, schema_path=None):
    """Validate *filename* against the matching schema using xmllint.

    *schema_root* may be an explicit schema file path or a schema-name root
    (e.g. ``'suite'``, ``'registry'``) resolved via :func:`find_schema_file`.
    """
    if not os.path.isfile(filename):
        raise CCPPError("validate_xml_file: Filename, '{}', does not exist".format(filename))
    if not os.access(filename, os.R_OK):
        raise CCPPError("validate_xml_file: Cannot open '{}'".format(filename))
    if os.path.isfile(schema_root):
        schema_file = schema_root
    else:
        if not schema_path:
            thispath = os.path.abspath(__file__)
            pdir = os.path.dirname(os.path.dirname(os.path.dirname(thispath)))
            schema_path = os.path.join(pdir, 'schema')
        schema_file = find_schema_file(schema_root, version, schema_path)
        if not (schema_file and os.path.isfile(schema_file)):
            verstring = '.'.join([str(x) for x in version])
            raise CCPPError(
                f"validate_xml_file: Cannot find schema for version {verstring},\n"
                f"            {schema_file} does not exist"
            )
    if not os.access(schema_file, os.R_OK):
        raise CCPPError(
            "validate_xml_file: Cannot open schema, '{}'".format(schema_file))

    xmllint = shutil.which('xmllint')
    if not xmllint:
        raise CCPPError(
            "validate_xml_file: xmllint not found, could not validate file {}".format(filename))

    logger.debug("Checking file {} against schema {}".format(filename, schema_file))
    cmd = [xmllint, '--noout', '--schema', schema_file, filename]
    cproc = subprocess.run(cmd, check=False, capture_output=True)
    if cproc.returncode == 0:
        # Some xmllint builds return 0 even when validation fails; double
        # check by looking for the literal 'validates' marker in output.
        result = b'validates' in cproc.stdout or b'validates' in cproc.stderr
    else:
        result = False
    if result:
        logger.debug(cproc.stdout)
        logger.debug(cproc.stderr)
        return result
    cmd_str = ' '.join(cmd)
    outstr = f"Execution of '{cmd_str}' failed with code: {cproc.returncode}\n"
    if cproc.stdout:
        outstr += f"{cproc.stdout.decode('utf-8', errors='replace').strip()}\n"
    if cproc.stderr:
        outstr += f"{cproc.stderr.decode('utf-8', errors='replace').strip()}\n"
    raise CCPPError(outstr)

"""Flat-module shim for original capgen's ``var_props`` module.

``write_init_files.py`` imports only the two boolean dimension
predicates ``is_horizontal_dimension`` and ``is_vertical_dimension``.
Both are tiny tabulated lookups; the full original ``var_props.py``
(~1500 lines) carries CCPP-Var-Dictionary machinery that CAM-SIMA
doesn't use here.  Reproduce the minimum surface.
"""


# Supported horizontal dimensions (verbatim from original
# ccpp_framework/scripts/var_props.py).
CCPP_HORIZONTAL_DIMENSIONS = [
    'ccpp_constant_one:horizontal_dimension',
    'ccpp_constant_one:horizontal_loop_extent',
    'horizontal_loop_begin:horizontal_loop_end',
    'horizontal_dimension',
    'horizontal_loop_extent',
]


# Supported vertical dimensions (verbatim).
CCPP_VERTICAL_DIMENSIONS = [
    'ccpp_constant_one:vertical_layer_dimension',
    'ccpp_constant_one:vertical_interface_dimension',
    'vertical_layer_dimension',
    'vertical_interface_dimension',
    'vertical_layer_index',
    'vertical_interface_index',
]


def is_horizontal_dimension(dim_name: str) -> bool:
    """Return True iff *dim_name* is a recognised horizontal dimension.

    Examples
    --------
    >>> is_horizontal_dimension('horizontal_loop_extent')
    True
    >>> is_horizontal_dimension('ccpp_constant_one:horizontal_dimension')
    True
    >>> is_horizontal_dimension('horizontal_loop_begin:horizontal_loop_end')
    True
    >>> is_horizontal_dimension('ccpp_constant_one')
    False
    """
    return dim_name in CCPP_HORIZONTAL_DIMENSIONS


def is_vertical_dimension(dim_name: str) -> bool:
    """Return True iff *dim_name* is a recognised vertical dimension.

    Examples
    --------
    >>> is_vertical_dimension('ccpp_constant_one:vertical_layer_dimension')
    True
    >>> is_vertical_dimension('vertical_layer_index')
    True
    >>> is_vertical_dimension('ccpp_constant_one:vertical_layer_index')
    False
    >>> is_vertical_dimension('horizontal_loop_extent')
    False
    """
    return dim_name in CCPP_VERTICAL_DIMENSIONS


__all__ = [
    'CCPP_HORIZONTAL_DIMENSIONS',
    'CCPP_VERTICAL_DIMENSIONS',
    'is_horizontal_dimension',
    'is_vertical_dimension',
]

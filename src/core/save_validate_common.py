"""Shared value checks of the save validator (pure, no game state).

Verbatim moves of the helpers ``valid_save_document`` used to define
inline; ``save_validate``, ``save_validate_entities`` and
``save_validate_weapons`` share them.
"""

import math


def finite_number(value) -> bool:
    try:
        return (isinstance(value, (int, float))
                and not isinstance(value, bool) and math.isfinite(value))
    except OverflowError:
        return False

def finite_tree(value, path=()) -> bool:
    if len(path) > 100:
        return False
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, (int, float)):
        return finite_number(value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_tree(item, path + (key,))
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(item, path + (index,))
                   for index, item in enumerate(value))
    return False

def bounded(value, low=0.0, high=1_000_000.0) -> bool:
    return finite_number(value) and low <= value <= high

def point(value, limit=1_000_000.0) -> bool:
    """An ``(x, y)`` pair of finite numbers within +/-``limit``."""
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(bounded(item, -limit, limit) for item in value))

def identity(value) -> bool:
    return type(value) is int and 1 <= value <= 2**63 - 1

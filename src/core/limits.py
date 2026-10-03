"""Hard bounds shared by the simulation, the save document and its validator.

They live outside ``game.py`` so the persistence mixin (``game_save``) and
the game itself import them from one place without a circular import.
"""

import math

MAX_AIR_PICTURE_TRACKS = 512
MAX_TRACK_DISPLAY_ID_LEN = 16
MAX_OPZ_TRACK_LABELS = 1024
MAX_SAVED_ENTITIES = 512
MAX_ENEMY_TORPEDOES = 128
MAX_DECOYS = 128
# Save-document bounds for pending and live missiles/torpedoes.
MAX_SAVED_ASMS = 512
MAX_SAVED_PLAYER_TORPEDOES = 128
MAX_SAVED_ESSMS = 128


def finite_number(value) -> bool:
    """A finite int or float, never a bool (the strict check of saved and
    authored numbers several models share)."""
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value))

"""Kompatibilitaets-Shim: Akustik-Datenbank lebt jetzt in src.data.catalog.

Alle Imports aus dieser Datei (TARGET_DATABASE, CIVILIAN_SIGNATURES,
signature_for_key, rank_signatures, TargetSignature) bleiben bestehen;
die Daten kommen aus dem Kontakt-Katalog (data/contacts/*.json oder
eingebauter Default).
"""

from src.data.catalog import CATALOG, TargetSignature, rank_signatures

TARGET_DATABASE = CATALOG.acoustic_profiles
SIGNATURES_BY_KEY = CATALOG.acoustic_by_key
CIVILIAN_SIGNATURES = CATALOG.civilian_signatures


def signature_for_key(key: str) -> TargetSignature | None:
    return SIGNATURES_BY_KEY.get(key)


assert len({s.key for s in TARGET_DATABASE
            if s.category not in ("BIOLOGISCH",)}) >= 100

"""Kontakt-Katalog: alle Plattformprofile (Akustik + Verhalten) an einer Stelle.

Die eingebauten Profile werden aus den paketierten ``data.contacts``-JSON-
Ressourcen geladen. Der Katalog enthält:

- 23 U-Boot-Profile (3 Legacy-Archetypen + 20 benannte Klassen)
- 25 feindliche Kampfschiffe (spawnbar, KAMPFSCHIFF)
- 55 zivile Schiffe (Tanker/Passagier/Fracht/Sonstiges)
- Flugzeugprofile (sonar-invisible, nur Radar/ESM)
- 3 Meerestier-Typen, 3 Torpedo-Profile, 1 Dekoy-Profil

Kontakte sind nie an ein einzelnes Profil gebunden: pro Instanz wird aus
Blätterzahl, Takt-Skala und Linien-Offsets ein Fingerprint gerollt
(src/data/fingerprint.py), damit zwei gleiche Klassen unterschiedlich klingen.
"""

import json
import os
from dataclasses import dataclass
from importlib import resources

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTACTS_DIR = os.path.join(_ROOT, "data", "contacts")

CIVIL_CATEGORIES = ("TANKER", "PASSAGIER", "FRACHT", "SONSTIGES")


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetSignature:
    """Akustisches Plattformprofil (passive Sonar-Klassifikation).

    blade_counts: mögliche Schrauben-Blätterzahlen
    rpm_range: (min, max) Wellendrehzahl 1/min (Klassifikation)
    tonal_band_hz: (min, max) Hz der Hauptschraube-Linie bei min..max Fahrt
    cavitation_tendency: 0 (stumm) .. 1 (leicht stark)
    broadband: (level, low_hz, high_hz) für die breitbandige Synthese, sonst None
    secondary_tonals: ((hz, amp, width), ...) z.B. Getriebe/Pumpen-Tonals
    """

    key: str
    label: str
    propulsion: str
    blade_counts: tuple
    rpm_range: tuple
    tonal_band_hz: tuple
    cavitation_tendency: float
    category: str = "FAHRZEUG"
    secondary_tonals: tuple = ()
    broadband: tuple = None
    signature_text: str = ""


@dataclass(frozen=True)
class SubProfile:
    key: str
    name: str
    speed_kn: tuple          # (min, max); max = Patrouillen-Fahrt
    max_depth_m: float
    torpedoes: int
    quiet: float             # 0 laut .. 1 stumm
    aggression: float
    spawn_weight: float
    acoustic: TargetSignature


@dataclass(frozen=True)
class SurfaceProfile:
    key: str
    name: str
    category: str            # TANKER/PASSAGIER/FRACHT/SONSTIGES/KAMPFSCHIFF
    hostile: bool
    speed_kn: tuple
    callsigns: tuple
    esm_prob: float          # P(Radar/ESM-Emitter an)
    asm_salvo: tuple         # (min, max) feindliche ASMs pro Salve
    asm_cooldown_s: float
    loiter_nm: float         # Patrouillen-Radius um Basis (nur feindlich)
    spawn_weight: float
    acoustic: TargetSignature


@dataclass(frozen=True)
class AircraftProfile:
    key: str
    name: str
    nation: str
    kind: str                # "civil" | "military"
    speed_kn: float
    esm: bool
    esm_range_nm: float
    loiter_nm: tuple         # (min, max)
    spawn_weight: float
    signature_text: str = ""


@dataclass(frozen=True)
class AnimalProfile:
    key: str
    name: str
    depth_min: float
    depth_max: float
    speed_kn: float
    quiet: float
    size_nm: float
    spawn_weight: float
    lines: tuple             # ((hz, amp, width), ...) biologische Tonalität
    signature_text: str = ""


@dataclass(frozen=True)
class TorpedoProfile:
    key: str
    name: str
    used_by: str             # "frigate" | "helo" | "enemy"
    speed_kn: float
    range_nm: float
    hit_dist_nm: float
    acoustic: TargetSignature = None


@dataclass(frozen=True)
class DecoyProfile:
    key: str
    name: str
    life_s: float
    speed_kn: float
    cooldown_s: float
    chance: float
    lines: tuple
    signature_text: str = ""


def build_catalog() -> "ContactCatalog":
    """Lädt den vollständigen eingebauten Katalog aus Paketressourcen."""
    return _load_catalog_from(resources.files("data.contacts"))


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------

class ContactCatalog:
    """Alle Plattformprofile + abgeleitete Listen (Spawn-Pools, Bibliothek)."""

    def __init__(self, subs, surfaces, aircraft, animals, torpedoes, decoys,
                 db_source: str = "data/contacts", library_signatures=()):
        self.subs = dict(subs)
        self.surfaces = dict(surfaces)
        self.aircraft = dict(aircraft)
        self.animals = dict(animals)
        self.torpedoes = dict(torpedoes)
        self.decoys = dict(decoys)
        self.db_source = db_source
        self.acoustic_by_key = {}
        for p in (list(self.subs.values()) + list(self.surfaces.values())):
            self.acoustic_by_key[p.acoustic.key] = p.acoustic
        for t in self.torpedoes.values():
            if t.acoustic is not None:
                self.acoustic_by_key[t.acoustic.key] = t.acoustic
        for signature in library_signatures:
            self.acoustic_by_key[signature.key] = signature
        self.acoustic_profiles = tuple(self.acoustic_by_key.values())
        self.civilian_signatures = tuple(
            s for s in self.acoustic_profiles
            if s.category in CIVIL_CATEGORIES)
        self.civilian_surfaces = tuple(
            p for p in self.surfaces.values() if not p.hostile)
        self.hostile_surfaces = tuple(
            p for p in self.surfaces.values() if p.hostile)

    # --- Auswahl-Hilfen (deterministisch über übergebene rng) ---

    def pick_surface(self, rng, hostile: bool = False):
        pool = (self.hostile_surfaces if hostile
                else self.civilian_surfaces)
        return _weighted_pick(rng, pool)

    def pick_sub(self, rng, pool=None):
        keys = pool if pool else list(self.subs.keys())
        pool = [self.subs[k] for k in keys if k in self.subs]
        if not pool:
            pool = list(self.subs.values())
        return _weighted_pick(rng, pool)

    def pick_aircraft(self, rng, kind: str):
        pool = [a for a in self.aircraft.values() if a.kind == kind]
        if not pool:
            pool = list(self.aircraft.values())
        return _weighted_pick(rng, pool)

    def pick_animal(self, rng):
        return _weighted_pick(rng, tuple(self.animals.values()))

    def get_torpedo(self, key: str):
        return self.torpedoes.get(key)

    def get_decoy(self, key: str):
        return self.decoys.get(key)

    def acoustic_for(self, key: str) -> TargetSignature | None:
        return self.acoustic_by_key.get(key)


def _weighted_pick(rng, pool):
    weights = [max(0.0, p.spawn_weight) for p in pool]
    total = sum(weights)
    if total <= 0:
        return rng.choice(pool)
    roll = rng.random() * total
    acc = 0.0
    for p, w in zip(pool, weights):
        acc += w
        if roll < acc:
            return p
    return pool[-1]


# ---------------------------------------------------------------------------
# JSON-Loader
# ---------------------------------------------------------------------------

def _read_entries(path) -> list:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path.name}: 'entries' fehlt/leer")
    return entries


def _pair(v, name: str) -> tuple:
    try:
        return (float(v[0]), float(v[1]))
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"{name}: Paar erwartet") from exc


def _acoustic_from_dict(d: dict, key: str, category_default: str,
                        label_default: str = "") -> TargetSignature:
    return TargetSignature(
        key=key, label=d.get("label", label_default or key),
        propulsion=d.get("propulsion", ""),
        blade_counts=tuple(int(b) for b in d.get("blades", ())),
        rpm_range=_pair(d.get("rpm_range", (0, 0)), "acoustic.rpm_range"),
        tonal_band_hz=_pair(d.get("tonal_band_hz", (0, 0)),
                            "acoustic.tonal_band_hz"),
        cavitation_tendency=float(d.get("cavitation_tendency", 0.0)),
        category=d.get("category", category_default),
        secondary_tonals=tuple(
            (float(t[0]), float(t[1]), float(t[2]))
            for t in d.get("secondary_tonals", ())),
        broadband=tuple(d["broadband"]) if d.get("broadband") else None,
        signature_text=d.get("signature_text", ""))


def _load_subs(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        acoustic = _acoustic_from_dict(e.get("acoustic", {}), key,
                                       "U_BOOT", e.get("name", key))
        out[key] = SubProfile(
            key=key, name=e.get("name", key),
            speed_kn=_pair(e.get("speed_kn", (6.0, 12.0)), "speed_kn"),
            max_depth_m=float(e.get("max_depth_m", 200.0)),
            torpedoes=int(e.get("torpedoes", 4)),
            quiet=float(e.get("quiet", 0.8)),
            aggression=float(e.get("aggression", 0.6)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            acoustic=acoustic)
    return out


def _load_surfaces(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        cat = e.get("category", "KAMPFSCHIFF")
        out[key] = SurfaceProfile(
            key=key, name=e.get("name", key), category=cat,
            hostile=bool(e.get("hostile", cat == "KAMPFSCHIFF")),
            speed_kn=_pair(e.get("speed_kn", (14.0, 24.0)), "speed_kn"),
            callsigns=tuple(e.get("callsigns", ())),
            esm_prob=float(e.get("esm_prob", 0.6)),
            asm_salvo=tuple(e.get("asm_salvo", (0, 0))),
            asm_cooldown_s=float(e.get("asm_cooldown_s", 240.0)),
            loiter_nm=float(e.get("loiter_nm", 0.0)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            acoustic=_acoustic_from_dict(e.get("acoustic", {}), key, cat,
                                         e.get("name", key)))
    return out


def _load_aircraft(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        out[key] = AircraftProfile(
            key=key, name=e.get("name", key),
            nation=e.get("nation", "ZIVIL"),
            kind=e.get("kind", "civil"),
            speed_kn=float(e.get(
                "speed_kn", 450.0 if e.get("kind") == "civil" else 200.0)),
            esm=bool(e.get("esm", False)),
            esm_range_nm=float(e.get("esm_range_nm", 0.0)),
            loiter_nm=_pair(e.get("loiter_nm", (0, 0)), "loiter_nm"),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            signature_text=e.get("signature_text", ""))
    return out


def _load_animals(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        out[key] = AnimalProfile(
            key=key, name=e.get("name", key),
            depth_min=float(e.get("depth_min", 10.0)),
            depth_max=float(e.get("depth_max", 50.0)),
            speed_kn=float(e.get("speed_kn", 2.0)),
            quiet=float(e.get("quiet", 0.5)),
            size_nm=float(e.get("size_nm", 0.3)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            lines=tuple((float(t[0]), float(t[1]), float(t[2]))
                        for t in e.get("lines", ())),
            signature_text=e.get("signature_text", ""))
    return out


def _load_torpedoes(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        acoustic = None
        if e.get("acoustic"):
            acoustic = _acoustic_from_dict(e["acoustic"], key, "FAHRZEUG",
                                           e.get("name", key))
        out[key] = TorpedoProfile(
            key=key, name=e.get("name", key),
            used_by=e.get("used_by", "enemy"),
            speed_kn=float(e.get("speed_kn", 28.0)),
            range_nm=float(e.get("range_nm", 30.0)),
            hit_dist_nm=float(e.get("hit_dist_nm", 0.25)),
            acoustic=acoustic)
    return out


def _load_decoys(path: str) -> dict:
    out = {}
    for e in _read_entries(path):
        key = str(e["key"])
        out[key] = DecoyProfile(
            key=key, name=e.get("name", key),
            life_s=float(e.get("life_s", 45.0)),
            speed_kn=float(e.get("speed_kn", 8.0)),
            cooldown_s=float(e.get("cooldown_s", 60.0)),
            chance=float(e.get("chance", 0.5)),
            lines=tuple((float(t[0]), float(t[1]), float(t[2]))
                        for t in e.get("lines", ())),
            signature_text=e.get("signature_text", ""))
    return out


def _load_library_signatures(path) -> tuple:
    return tuple(
        _acoustic_from_dict(entry, str(entry["key"]),
                            entry.get("category", "FAHRZEUG"))
        for entry in _read_entries(path)
    )


def _validate(cat: ContactCatalog) -> None:
    n_platforms = sum(1 for s in cat.acoustic_profiles
                      if s.category != "BIOLOGISCH")
    if n_platforms < 100:
        raise ValueError(f"zu wenige Plattformprofile ({n_platforms} < 100)")
    for key in ("diesel_alt", "aip_modern", "ssn"):
        if key not in cat.subs:
            raise ValueError(f"U-Boot-Prototyp '{key}' fehlt")
    if "enemy_torp" not in cat.torpedoes:
        raise ValueError("Torpedo-Profil 'enemy_torp' fehlt")
    if "decoy" not in cat.decoys:
        raise ValueError("Dekoy-Profil 'decoy' fehlt")
    cats = {p.category for p in cat.civilian_surfaces}
    if not set(CIVIL_CATEGORIES).issubset(cats):
        raise ValueError("zivile Kategorien unvollständig")
    if not cat.aircraft or not cat.animals:
        raise ValueError("Flugzeuge/Tiere fehlen")
    for s in cat.acoustic_profiles:
        if not (0.0 <= s.cavitation_tendency <= 1.0):
            raise ValueError(f"cavitation ausserhalb 0..1: {s.key}")
        # (0, 0) = "kein Band" (z.B. biologische Quellen, Torpedos)
        if s.tonal_band_hz[0] > 0.0 and s.tonal_band_hz[0] >= s.tonal_band_hz[1]:
            raise ValueError(f"tonal_band inversed: {s.key}")
        if s.rpm_range[0] > 0.0 and s.rpm_range[0] >= s.rpm_range[1]:
            raise ValueError(f"rpm_range inversed: {s.key}")
        if s.broadband and s.broadband[1] >= s.broadband[2]:
            raise ValueError(f"broadband-Band inversed: {s.key}")


def _load_catalog_from(base_dir) -> ContactCatalog:
    cat = ContactCatalog(
        _load_subs(base_dir / "subs.json"),
        _load_surfaces(base_dir / "warships.json") |
        _load_surfaces(base_dir / "civilians.json"),
        _load_aircraft(base_dir / "aircraft.json"),
        _load_animals(base_dir / "animals.json"),
        _load_torpedoes(base_dir / "torpedoes.json"),
        _load_decoys(base_dir / "decoys.json"),
        db_source=base_dir.name or "data/contacts",
        library_signatures=_load_library_signatures(
            base_dir / "acoustics.json"))
    _validate(cat)
    return cat


def load_catalog(base_dir: str = None, quiet: bool = False) -> ContactCatalog:
    """Lädt einen Katalog; fehlerhafte externe Daten fallen auf Paketdaten zurück."""
    if base_dir is None:
        return build_catalog()
    source = os.fspath(base_dir)
    try:
        from pathlib import Path
        return _load_catalog_from(Path(source))
    except Exception as exc:  # noqa: BLE001 - external data may be user-edited
        if not quiet:
            import sys
            print(f"[kontakt-db] {source}: {exc} - "
                  f"verwende paketierten Katalog", file=sys.stderr)
        return build_catalog()


def rank_signatures(blade_rate_hz: float | None, rpm: float | None,
                    tonal_hz: float | None, cavitation: float
                    ) -> list[tuple[TargetSignature, float]]:
    """Transparente 0..1-Ähnlichkeitswerte fuer die Operator-Analyse.

    Bewertet gegen alle Plattformprofile des aktiven Katalogs
    (ohne BIOLOGISCH-Fangnetz-Profile? Nein: alle Eintraege, wie zuvor).
    """
    signatures = CATALOG.acoustic_profiles
    if blade_rate_hz is None:
        return [(signature, 0.0) for signature in signatures]
    result = []
    for signature in signatures:
        score = 0.0
        rpm_options = ([rpm] if rpm is not None else
                       [blade_rate_hz * 60.0 / blades
                        for blades in signature.blade_counts])
        if signature.blade_counts and any(
                signature.rpm_range[0] <= value <= signature.rpm_range[1]
                for value in rpm_options):
            score += 0.45
        if tonal_hz is not None and (
                signature.tonal_band_hz[0] <= tonal_hz <= signature.tonal_band_hz[1]):
            score += 0.30
        if signature.blade_counts and rpm is not None:
            estimated_blades = round(blade_rate_hz * 60.0 / rpm)
            if estimated_blades in signature.blade_counts:
                score += 0.10
        score += max(0.0, 0.15 - abs(cavitation - signature.cavitation_tendency) * 0.15)
        result.append((signature, round(min(1.0, score), 3)))
    return sorted(result, key=lambda item: item[1], reverse=True)


CATALOG = load_catalog()

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
import math
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

    @property
    def is_nuclear(self) -> bool:
        """Capability metadata from the JSON propulsion label, not the profile ID."""
        return self.acoustic.propulsion == "elektrisch/Kernantrieb"

    @property
    def requires_air(self) -> bool:
        """Diesel and AIP profiles periodically require air; no endurance model."""
        return not self.is_nuclear


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

CONTACT_FIELDS = {
    "subs.json": {"key", "name", "speed_kn", "max_depth_m", "torpedoes",
                  "quiet", "aggression", "spawn_weight", "acoustic"},
    "warships.json": {"key", "name", "category", "hostile", "speed_kn",
                      "callsigns", "esm_prob", "asm_salvo", "asm_cooldown_s",
                      "loiter_nm", "spawn_weight", "acoustic"},
    "aircraft.json": {"key", "name", "nation", "kind", "speed_kn", "esm",
                      "esm_range_nm", "loiter_nm", "spawn_weight", "signature_text"},
    "animals.json": {"key", "name", "depth_min", "depth_max", "speed_kn",
                     "quiet", "size_nm", "spawn_weight", "lines", "signature_text"},
    "torpedoes.json": {"key", "name", "used_by", "speed_kn", "range_nm", "hit_dist_nm"},
    "decoys.json": {"key", "name", "life_s", "speed_kn", "cooldown_s",
                    "chance", "lines", "signature_text"},
    "acoustics.json": {"key", "label", "propulsion", "blades", "rpm_range",
                       "tonal_band_hz", "cavitation_tendency", "category",
                       "secondary_tonals", "broadband", "signature_text"},
}
CONTACT_FIELDS["civilians.json"] = CONTACT_FIELDS["warships.json"]
ACOUSTIC_FIELDS = CONTACT_FIELDS["acoustics.json"] - {"key"}
ACOUSTIC_CATEGORIES = (*CIVIL_CATEGORIES, "KAMPFSCHIFF", "U_BOOT", "FAHRZEUG", "BIOLOGISCH")


def _schema_object(value, fields, where, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: object expected")
    missing = fields - set(optional) - value.keys()
    extra = value.keys() - fields
    if missing or extra:
        raise ValueError(f"{where}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")


def _schema_number(value, where, low=0, high=None, positive=False, integer=False):
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise ValueError(f"{where}: {'integer' if integer else 'number'} expected")
    # Comparing integers directly avoids overflowing float conversion on hostile JSON.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{where}: finite number expected")
    if value < low or (positive and value <= 0) or (high is not None and value > high):
        raise ValueError(f"{where}: number outside allowed range")
    if abs(value) > 1e100:
        raise ValueError(f"{where}: number outside safe range")


def _schema_text(value, where):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(f"{where}: non-empty string of at most 500 characters expected")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{where}: control characters not allowed")


def _schema_pair(value, where, high, equal=False, integer=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{where}: two-item array expected")
    for item in value:
        _schema_number(item, where, high=high, integer=integer)
    if value[0] > value[1] or (not equal and value[0] == value[1]):
        raise ValueError(f"{where}: range must be ordered")


def _schema_lines(value, where):
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError(f"{where}: array of at most 256 lines expected")
    for line in value:
        if not isinstance(line, list) or len(line) != 3:
            raise ValueError(f"{where}: three-item array expected")
        _schema_number(line[0], where, high=100000, positive=True)
        _schema_number(line[1], where, high=1)
        _schema_number(line[2], where, high=10000, positive=True)


def _schema_acoustic(value, where, category=None):
    _schema_object(value, ACOUSTIC_FIELDS, where)
    for field in ("label", "propulsion", "signature_text"):
        _schema_text(value[field], f"{where}.{field}")
    blades = value["blades"]
    if not isinstance(blades, list) or len(blades) > 20:
        raise ValueError(f"{where}.blades: positive integer array expected")
    for blade in blades:
        _schema_number(blade, f"{where}.blades", low=1, high=20, integer=True)
    if len(set(blades)) != len(blades):
        raise ValueError(f"{where}.blades: duplicate value")
    for field in ("rpm_range", "tonal_band_hz"):
        band = value[field]
        _schema_pair(band, f"{where}.{field}", 100000, equal=band == [0, 0])
    _schema_number(value["cavitation_tendency"], f"{where}.cavitation_tendency", high=1)
    if value["category"] not in ACOUSTIC_CATEGORIES or (
            category is not None and value["category"] != category):
        raise ValueError(f"{where}.category: invalid category")
    _schema_lines(value["secondary_tonals"], f"{where}.secondary_tonals")
    broadband = value["broadband"]
    if broadband is not None:
        if not isinstance(broadband, list) or len(broadband) != 3:
            raise ValueError(f"{where}.broadband: null or three-item array expected")
        _schema_number(broadband[0], f"{where}.broadband", high=1)
        _schema_pair(broadband[1:], f"{where}.broadband", 100000)
        _schema_number(broadband[1], f"{where}.broadband", positive=True)


def validate_contact_entry(filename, entry, where="entry"):
    """Strict JSON schema shared by the package loader and offline validator.

    Bounds are defensive authoring limits, not real-platform performance claims.
    Editor documents have their own versioned schema and are not runtime profiles.
    """
    optional = {"acoustic"} if filename == "torpedoes.json" else set()
    _schema_object(entry, CONTACT_FIELDS[filename] | optional, where, optional)
    _schema_text(entry["key"], f"{where}.key")
    if filename == "acoustics.json":
        _schema_acoustic({k: v for k, v in entry.items() if k != "key"}, where)
        return
    _schema_text(entry["name"], f"{where}.name")
    for field in ("nation", "signature_text"):
        if field in entry:
            _schema_text(entry[field], f"{where}.{field}")
    for field in ("hostile", "esm"):
        if field in entry and type(entry[field]) is not bool:
            raise ValueError(f"{where}.{field}: boolean expected")
    for field, maximum in (("quiet", 1), ("aggression", 1), ("esm_prob", 1),
                           ("chance", 1), ("spawn_weight", 100000),
                           ("depth_min", 2000), ("depth_max", 2000),
                           ("esm_range_nm", 5000)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum)
    for field, maximum in (("max_depth_m", 2000), ("range_nm", 5000),
                           ("hit_dist_nm", 100), ("size_nm", 100),
                           ("life_s", 604800), ("cooldown_s", 604800)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum, positive=True)
    if "lines" in entry:
        _schema_lines(entry["lines"], f"{where}.lines")
    if filename in ("subs.json", "warships.json", "civilians.json"):
        _schema_pair(entry["speed_kn"], f"{where}.speed_kn", 1000)
        category = "U_BOOT" if filename == "subs.json" else entry["category"]
        _schema_acoustic(entry["acoustic"], f"{where}.acoustic", category)
    else:
        _schema_number(entry["speed_kn"], f"{where}.speed_kn", high=5000,
                       positive=filename != "animals.json")
    if filename == "subs.json":
        _schema_number(entry["torpedoes"], f"{where}.torpedoes", high=100, integer=True)
        if entry["acoustic"]["propulsion"] not in (
                "Diesel-elektrisch", "elektrisch/AIP", "elektrisch/Kernantrieb"):
            raise ValueError(f"{where}.acoustic.propulsion: invalid submarine propulsion")
    elif filename in ("warships.json", "civilians.json"):
        allowed = ("KAMPFSCHIFF",) if filename == "warships.json" else CIVIL_CATEGORIES
        if entry["category"] not in allowed:
            raise ValueError(f"{where}.category: invalid surface category")
        if entry["hostile"] != (filename == "warships.json"):
            raise ValueError(f"{where}.hostile: does not match surface catalog")
        callsigns = entry["callsigns"]
        if not isinstance(callsigns, list) or len(callsigns) > 256:
            raise ValueError(f"{where}.callsigns: string array expected")
        for callsign in callsigns:
            _schema_text(callsign, f"{where}.callsigns")
        _schema_pair(entry["asm_salvo"], f"{where}.asm_salvo", 100, equal=True, integer=True)
        _schema_number(entry["asm_cooldown_s"], f"{where}.asm_cooldown_s", high=604800)
        _schema_number(entry["loiter_nm"], f"{where}.loiter_nm", high=5000)
    elif filename == "aircraft.json":
        if entry["kind"] not in ("civil", "military"):
            raise ValueError(f"{where}.kind: invalid aircraft kind")
        _schema_pair(entry["loiter_nm"], f"{where}.loiter_nm", 5000, equal=True)
    elif filename == "animals.json":
        if entry["depth_min"] >= entry["depth_max"]:
            raise ValueError(f"{where}: depth range must be ordered")
    elif filename == "torpedoes.json":
        if entry["used_by"] not in ("frigate", "helo", "enemy"):
            raise ValueError(f"{where}.used_by: invalid torpedo owner")
        if "acoustic" in entry:
            _schema_acoustic(entry["acoustic"], f"{where}.acoustic", "FAHRZEUG")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_entries(path) -> list:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=_unique_json_object)
    _schema_object(data, {"version", "entries"}, path.name)
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError(f"{path.name}.version: unsupported schema version")
    entries = data["entries"]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path.name}.entries: non-empty array expected")
    seen = set()
    for index, entry in enumerate(entries):
        where = f"{path.name}.entries[{index}]"
        validate_contact_entry(path.name, entry, where)
        if entry["key"] in seen:
            raise ValueError(f"{where}: duplicate key {entry['key']!r}")
        seen.add(entry["key"])
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
    groups = (
        _load_subs(base_dir / "subs.json"),
        _load_surfaces(base_dir / "warships.json"),
        _load_surfaces(base_dir / "civilians.json"),
        _load_aircraft(base_dir / "aircraft.json"),
        _load_animals(base_dir / "animals.json"),
        _load_torpedoes(base_dir / "torpedoes.json"),
        _load_decoys(base_dir / "decoys.json"),
    )
    seen = set()
    for group in groups:
        duplicates = seen.intersection(group)
        if duplicates:
            raise ValueError(f"duplicate profile ID: {sorted(duplicates)}")
        seen.update(group)
    library = _load_library_signatures(base_dir / "acoustics.json")
    if {signature.key for signature in library} != {"animal", *groups[6]}:
        raise ValueError("acoustics.json: must define animal and every decoy library signature")
    # Decoy library aliases are intentional; no library entry may shadow a platform.
    if any(signature.key in group for signature in library for group in groups[:6]):
        raise ValueError("acoustics.json: duplicate platform/library key")
    cat = ContactCatalog(
        groups[0], groups[1] | groups[2], *groups[3:],
        db_source=base_dir.name or "data/contacts",
        library_signatures=library)
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

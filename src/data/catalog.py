"""Kontakt-Katalog: alle Plattformprofile (Akustik + Verhalten) an einer Stalle.

Primärquelle: data/contacts/*.json (erweiterbar, Schema in docs/contacts-db.md).
Fehlt ein Verzeichnis oder ist eine Datei kaputt, wird der eingebaute
Default-Katalog verwendet (identische Werte, wie sie tools/gen_contacts.py
exportiert). Der Katalog enthält:

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


# ---------------------------------------------------------------------------
# Eingebauter Default (gleiche Werte wie der JSON-Export)
# ---------------------------------------------------------------------------

# Akustische Familien: (propulsion, blades, rpm, tonal_band, cav,
#                       broadband(level,lo,hi), signature_text)
FAMILY_ACOUSTIC = {
    "sub_nuclear": ("elektrisch/Kernantrieb", (5, 7), (120.0, 360.0),
                    (12.0, 40.0), 0.20, (0.15, 30.0, 250.0),
                    "sehr leise, gleichmäßig (Kern?)"),
    "sub_aip": ("elektrisch/AIP", (5, 7), (45.0, 150.0),
                (6.0, 25.0), 0.15, (0.10, 25.0, 180.0),
                "leise, elektrischer Antrieb"),
    "sub_diesel": ("Diesel-elektrisch", (4, 5), (90.0, 220.0),
                   (8.0, 22.0), 0.65, (0.40, 30.0, 250.0),
                   "Diesel-Propeller, deutlich hörbar"),
    "warship": ("Diesel/Gasturbine", (4, 5, 6), (200.0, 700.0),
                (18.0, 190.0), 0.55, (0.55, 40.0, 300.0),
                "kräftige Gasturbinen-Tonals"),
    "tanker": ("langsamer Diesel", (4, 5, 6), (90.0, 420.0),
               (12.0, 130.0), 0.72, (0.45, 30.0, 250.0),
               "langsamer Mahlrhythmus"),
    "passenger": ("Mehrfachdiesel/Getriebe", (4, 5, 6), (120.0, 650.0),
                  (15.0, 175.0), 0.68, (0.50, 40.0, 300.0),
                  "Mehrfachdiesel, Getriebe"),
    "cargo": ("Diesel/Getriebe", (4, 5, 6), (100.0, 500.0),
              (14.0, 160.0), 0.78, (0.55, 40.0, 300.0),
              "stetiger Frachter-Mahl"),
    "aux": ("Diesel/Arbeitsmaschine", (3, 4, 5), (180.0, 1100.0),
            (20.0, 240.0), 0.88, (0.60, 50.0, 320.0),
            "Arbeitsmaschine, unregelmäßig"),
}

# Sekundäre Tonals (Getriebe/Pumpen) pro Familie – optional, modellhaft
FAMILY_SECONDARY = {
    "warship": ((25.0, 0.25, 2.0),),
    "passenger": ((30.0, 0.20, 2.0),),
    "aux": ((40.0, 0.30, 3.0),),
}

# (key, name, family, speed_kn, max_depth_m, torpedoes, quiet, aggression,
#  spawn_weight)
SUB_ENTRIES = (
    # Legacy-Archetypen (Spielverhalt unverändert gegenüber v1)
    ("diesel_alt", "Altmetall (Diesel, älter)", "sub_diesel", (6.0, 11.0),
     200.0, 4, 0.75, 0.5, 1.0),
    ("aip_modern", "Geisterschwärmer (AIP-modern)", "sub_aip", (7.0, 13.0),
     250.0, 5, 0.85, 0.7, 1.0),
    ("ssn", "Knochenbrecher (Nuklear)", "sub_nuclear", (12.0, 18.0),
     400.0, 8, 0.92, 1.0, 0.8),
    # Benannte Klassen (Modellannahmen, nicht verifizierte Daten)
    ("sub_01", "Type 212CD", "sub_aip", (10.0, 13.0), 250.0, 5, 0.88, 0.7, 0.5),
    ("sub_02", "Type 214", "sub_aip", (10.0, 13.0), 250.0, 5, 0.88, 0.7, 0.5),
    ("sub_03", "Virginia-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.92, 1.0, 0.5),
    ("sub_04", "Los-Angeles-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.90, 0.9, 0.5),
    ("sub_05", "Seawolf-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.93, 1.0, 0.5),
    ("sub_06", "Astute-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.92, 0.9, 0.5),
    ("sub_07", "Trafalgar-Klasse", "sub_diesel", (8.0, 12.0), 200.0, 4,
     0.82, 0.6, 0.5),
    ("sub_08", "Rubis-Klasse", "sub_diesel", (8.0, 12.0), 200.0, 4,
     0.80, 0.6, 0.5),
    ("sub_09", "Suffren-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.92, 0.9, 0.5),
    ("sub_10", "Scorpene-Klasse", "sub_aip", (10.0, 13.0), 250.0, 5,
     0.86, 0.6, 0.5),
    ("sub_11", "Kilo-Klasse", "sub_diesel", (8.0, 12.0), 200.0, 4,
     0.78, 0.7, 0.5),
    ("sub_12", "Improved-Kilo", "sub_aip", (10.0, 13.0), 250.0, 5,
     0.86, 0.7, 0.5),
    ("sub_13", "Lada-Klasse", "sub_aip", (10.0, 13.0), 250.0, 5,
     0.86, 0.7, 0.5),
    ("sub_14", "Yasen-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.94, 1.0, 0.5),
    ("sub_15", "Oscar-II-Klasse", "sub_nuclear", (12.0, 16.0), 400.0, 12,
     0.88, 1.0, 0.5),
    ("sub_16", "Akula-Klasse", "sub_nuclear", (12.0, 16.0), 400.0, 12,
     0.88, 1.0, 0.5),
    ("sub_17", "Borei-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.95, 1.0, 0.5),
    ("sub_18", "Collins-Klasse", "sub_nuclear", (14.0, 18.0), 400.0, 8,
     0.92, 0.9, 0.5),
    ("sub_19", "Soryu-Klasse", "sub_aip", (10.0, 13.0), 250.0, 5,
     0.88, 0.7, 0.5),
    ("sub_20", "Taigei-Klasse", "sub_aip", (10.0, 13.0), 250.0, 5,
     0.88, 0.7, 0.5),
)

WARP_SHIP_NAMES = (
    "Arleigh-Burke-Zerstoerer", "Ticonderoga-Kreuzer", "Zumwalt-Zerstoerer",
    "Type-45-Zerstoerer", "Type-23-Fregatte", "Type-26-Fregatte",
    "F124-Fregatte", "F125-Fregatte", "Sachsen-Fregatte",
    "Baden-Wuerttemberg-Fregatte", "De-Zeven-Provincien-Fregatte",
    "Horizon-Zerstoerer", "FREMM-Fregatte", "La-Fayette-Fregatte",
    "Visby-Korvette", "Iver-Huitfeldt-Fregatte", "Nansen-Fregatte",
    "KDX-III-Zerstoerer", "Mogami-Fregatte", "Atago-Zerstoerer",
    "Akizuki-Zerstoerer", "Kirov-Kreuzer", "Udaloy-Zerstoerer",
    "Admiral-Gorshkov-Fregatte", "Type-055-Zerstoerer",
)

# (key_prefix, akustische Familie, Kategorie, Namen)
CIVILIAN_FAMILIES = (
    ("tanker", "tanker", "TANKER", (
        "Lewis-and-Clark-Versorger", "John-Lewis-Tanker", "Tide-Klasse",
        "Berlin-Klasse-Versorger", "Wave-Klasse-Tanker", "Aegir-Klasse",
        "Vulcano-Versorger", "Etna-Versorger", "Supply-Klasse",
        "Maersk-Triple-E", "VLCC-Tanker", "Aframax-Tanker",
        "Suezmax-Tanker", "Q-Max-LNG-Tanker", "Shuttle-Tanker")),
    ("passenger", "passenger", "PASSAGIER", (
        "Queen-Mary-2", "Oasis-Kreuzfahrer", "Icon-Kreuzfahrer",
        "Disney-Wish", "AIDAnova", "MSC-Seashore", "Mein-Schiff",
        "Color-Magic-Faehre", "Stena-Britannica", "DFDS-RoPax",
        "Hurtigruten-Expedition", "Arctic-Expedition-Schiff",
        "River-Cruise-Schiff", "Schnellfaehre", "Nachtfaehre")),
    ("cargo", "cargo", "FRACHT", (
        "Emma-Maersk", "Ever-Given-Klasse", "Hapag-Lloyd-Containerschiff",
        "Feeder-Containerschiff", "Panamax-Containerschiff", "Handymax-Bulker",
        "RoRo-Frachter", "Autotransporter", "Kuehlfrachter",
        "Bulk-Carrier", "Heavy-Lift-Schiff", "General-Cargo-Schiff",
        "Container-Feeder", "Mehrzweckfrachter", "Kuestenfrachter")),
    ("aux", "aux", "SONSTIGES", (
        "Minenabwehrfahrzeug", "Hafenschlepper", "Seenotrettungskreuzer",
        "Forschungsschiff", "Kabelleger", "Offshore-Versorger",
        "Fischtrawler", "Vermessungsschiff", "Bergungsschlepper",
        "Lotsenboot")),
)

# Rufzeichen-Pools je Kategorie (AIS/Brückenauskunft)
CALLSIGN_POOLS = {
    "TANKER": ("MV NORDWIND", "MV BALTICA", "MV OZEANSTERNE", "MV WINDSTILL",
               "MT NORDSEE", "MT HAVBRAK", "MV EIDER", "MT POLARIS"),
    "PASSAGIER": ("SS FJORDLAND", "SS HAVBRAK", "SS NORDSEE", "MS POLARIS",
                  "MS BORENSUND", "FV KALVSVIK", "MS VIKINGFJORD",
                  "FV SVALBAREN"),
    "FRACHT": ("MV KOTKA", "MV BALTISC", "CV NORDSTERN", "MV OSTSEEWIND",
               "MV KURELA", "CV BALTIK", "MV SKAGERRAK", "CV TROLLFJORD"),
    "SONSTIGES": ("PS HELIOS", "SV BOREN-RECHER", "MS SEEBRUECKE",
                  "PS LEUCHT-4", "SV OZEANFORSCHER", "MS KANALBAHN",
                  "PS HAFEN-7", "SV VERMESSER"),
}

_AIRCRAFT_DEFAULTS = (
    AircraftProfile("mil_patrol", "BOREN Patrouille", "BOREN", "military",
                    200.0, True, 60.0, (15.0, 30.0), 1.0,
                    "militärisch, nur ESM/Radar"),
    AircraftProfile("civil_transit", "Ziviler Verkehrsflug", "HANSE", "civil",
                    450.0, False, 0.0, (0.0, 0.0), 1.0,
                    "ziviler Transport, nur Radar"),
)

_ANIMAL_DEFAULTS = (
    AnimalProfile("whale", "Wal", 80.0, 200.0, 4.0, 0.45, 0.5, 1.0,
                  ((32.0, 0.55, 3.0), (45.0, 0.35, 2.0)),
                  "Gesang, periodisch, tieffrequenz"),
    AnimalProfile("fish_school", "Fischschwarm", 30.0, 80.0, 1.0, 0.60, 0.3,
                  1.0, ((90.0, 0.25, 6.0), (140.0, 0.18, 5.0)),
                  "Knistern/Schlecken, unregelmäßig"),
    AnimalProfile("jellyfish", "Quallen", 5.0, 25.0, 0.2, 0.75, 0.2, 1.0,
                  ((180.0, 0.12, 4.0),),
                  "kaum hörbar, leises Platschen"),
)

_TORPEDO_DEFAULTS = (
    TorpedoProfile("frigate_torp", "Drahttorpedo (Fregatte)", "frigate",
                   45.0, 12.0, 0.135, None),
    TorpedoProfile("helo_torp", "Leichttorpedo (HSP-5)", "helo",
                   55.0, 12.0, 0.135, None),
    TorpedoProfile("enemy_torp", "Feindtorpedo", "enemy",
                   28.0, 30.0, 0.25,
                   TargetSignature("enemy_torp", "Feindtorpedo",
                                   "Torpedorantrieb", (), (0.0, 0.0),
                                   (90.0, 150.0), 0.90, "FAHRZEUG",
                                   (), (0.50, 80.0, 300.0),
                                   "aggressives, hochfrequentes Kreischen")),
)

_DECOY_DEFAULTS = (
    DecoyProfile("decoy", "Akustischer Dekoy", 45.0, 8.0, 60.0, 0.5,
                 ((120.0, 0.9, 8.0), (75.0, 0.4, 3.0)),
                 "kurzes lautes Rauschen"),
)

# Eintrag für die Akustik-Bibliothek (BIOLOGISCH, kein Spawn)
_ANIMAL_LIBRARY_SIG = TargetSignature(
    "animal", "Biologischer Kontakt", "nicht mechanisch", (), (0.0, 0.0),
    (0.0, 300.0), 0.0, "BIOLOGISCH", (), None,
    "biologisches Signal (Tier?)")

_DECOY_LIBRARY_SIG = TargetSignature(
    "decoy", "Akustischer Dekoy", "Puls-/Rauschquelle", (), (0.0, 0.0),
    (40.0, 180.0), 0.90, "FAHRZEUG", (), (0.80, 40.0, 300.0),
    "kurzes lautes Rauschen")


def _series_signature(prefix: str, index: int, name: str, family: str,
                      category: str) -> TargetSignature:
    """Individuell unterscheidbare Signatur aus einer Familie (gleiche
    Shift-Formel wie die ursprüngliche 100-Profile-Datenbank)."""
    propulsion, blades, rpm, tonal, cav, bb, text = FAMILY_ACOUSTIC[family]
    rpm_shift = (index % 5 - 2) * 7.0
    tone_shift = (index % 4 - 1.5) * 1.5
    return TargetSignature(
        key=f"{prefix}_{index + 1:02d}", label=name, propulsion=propulsion,
        blade_counts=blades,
        rpm_range=(max(20.0, rpm[0] + rpm_shift), rpm[1] + rpm_shift),
        tonal_band_hz=(max(1.0, tonal[0] + tone_shift),
                       tonal[1] + tone_shift),
        cavitation_tendency=max(0.0, min(1.0,
                                         cav + (index % 3 - 1) * 0.04)),
        category=category,
        secondary_tonals=FAMILY_SECONDARY.get(family, ()),
        broadband=bb, signature_text=text)


def build_catalog() -> "ContactCatalog":
    """Eingebauter Default-Katalog (Referenz für tools/gen_contacts.py)."""
    subs = {}
    for (key, name, family, speed, depth, torps, quiet, agg,
         weight) in SUB_ENTRIES:
        propulsion, blades, rpm, tonal, cav, bb, text = \
            FAMILY_ACOUSTIC[family]
        sig = TargetSignature(
            key=key, label=name, propulsion=propulsion, blade_counts=blades,
            rpm_range=rpm, tonal_band_hz=tonal,
            cavitation_tendency=cav, category="U_BOOT",
            secondary_tonals=(), broadband=bb, signature_text=text)
        subs[key] = SubProfile(key, name, speed, depth, torps, quiet,
                               agg, weight, sig)

    surfaces = {}
    civilian_speeds = {
        "TANKER": (10.0, 16.0),
        "PASSAGIER": (18.0, 25.0),
        "FRACHT": (12.0, 20.0),
        "SONSTIGES": (8.0, 16.0),
    }
    for prefix, family, category, names in CIVILIAN_FAMILIES:
        for i, name in enumerate(names):
            key = f"{prefix}_{i + 1:02d}"
            surfaces[key] = SurfaceProfile(
                key, name, category, False, civilian_speeds[category],
                CALLSIGN_POOLS[category], 0.6, (0, 0), 0.0, 0.0, 1.0,
                _series_signature(prefix, i, name, family, category))
    for i, name in enumerate(WARP_SHIP_NAMES):
        key = f"warship_{i + 1:02d}"
        surfaces[key] = SurfaceProfile(
            key, name, "KAMPFSCHIFF", True, (12.0, 28.0), (), 1.0, (2, 4),
            900.0, 20.0, 1.0,
            _series_signature("warship", i, name, "warship", "KAMPFSCHIFF"))

    aircraft = {a.key: a for a in _AIRCRAFT_DEFAULTS}
    animals = {a.key: a for a in _ANIMAL_DEFAULTS}
    torpedoes = {t.key: t for t in _TORPEDO_DEFAULTS}
    decoys = {d.key: d for d in _DECOY_DEFAULTS}
    return ContactCatalog(subs, surfaces, aircraft, animals, torpedoes,
                          decoys, db_source="eingebauter Default")


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------

class ContactCatalog:
    """Alle Plattformprofile + abgeleitete Listen (Spawn-Pools, Bibliothek)."""

    def __init__(self, subs, surfaces, aircraft, animals, torpedoes, decoys,
                 db_source: str = "data/contacts"):
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
        for d in self.decoys.values():
            self.acoustic_by_key[d.key] = _DECOY_LIBRARY_SIG
        self.acoustic_by_key[_ANIMAL_LIBRARY_SIG.key] = _ANIMAL_LIBRARY_SIG
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

def _read_entries(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{os.path.basename(path)}: 'entries' fehlt/leer")
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


def load_catalog(base_dir: str = None, quiet: bool = False) -> ContactCatalog:
    """Lädt data/contacts/*.json; bei Fehlern: eingebauter Default.

    db_source auf dem Katalog zeigt, welche Quelle aktiv ist
    ("data/contacts" oder "eingebauter Default").
    """
    base_dir = base_dir or CONTACTS_DIR
    try:
        cat = ContactCatalog(
            _load_subs(os.path.join(base_dir, "subs.json")),
            _load_surfaces(os.path.join(base_dir, "warships.json")) |
            _load_surfaces(os.path.join(base_dir, "civilians.json")),
            _load_aircraft(os.path.join(base_dir, "aircraft.json")),
            _load_animals(os.path.join(base_dir, "animals.json")),
            _load_torpedoes(os.path.join(base_dir, "torpedoes.json")),
            _load_decoys(os.path.join(base_dir, "decoys.json")),
            db_source=os.path.basename(base_dir) or "data/contacts")
        _validate(cat)
        return cat
    except Exception as exc:  # noqa: BLE001 – Fallback ist Absicht
        if not quiet:
            import sys
            print(f"[kontakt-db] {base_dir}: {exc} – "
                  f"verwende eingebauten Default-Katalog", file=sys.stderr)
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

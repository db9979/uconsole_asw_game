"""Catalog profile records: the frozen dataclasses of every platform,
acoustic and v2 system profile, plus the civilian categories and the hostile
surface pool.  Moved verbatim from ``catalog.py``, which re-exports them.
"""

from dataclasses import dataclass


CIVIL_CATEGORIES = ("TANKER", "PASSAGIER", "FRACHT", "SONSTIGES")
# Random hostile-surface spawns are drawn only from this pool (not from
# spawn_weight across all KAMPFSCHIFF entries) - kept to Russian-Federation
# classes so a random scenario's enemy surface units are Russia by default.
# Other real navies remain in the catalog as neutral civilians.json traffic
# (category "SONSTIGES") and via explicit mission-editor placement.
LEGACY_HOSTILE_SURFACE_KEYS = ("warship_22", "warship_23", "warship_24", "warship_29")


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
    # Optional, authoring-may-be-absent extensions (Wikipedia-Import-Editor):
    lofar_base_freq_hz: tuple = ()
    cavitation_speed_knots: float | None = None
    audio_sample_id: str = ""


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
    wiki_url: str | None = None
    default_faction: str | None = None
    rcs_m2: float | None = None

    @property
    def is_nuclear(self) -> bool:
        """Capability metadata from the JSON propulsion label, not the profile ID."""
        return self.acoustic.propulsion == "elektrisch/Kernantrieb"

    @property
    def requires_air(self) -> bool:
        """Diesel and AIP profiles require an endurance component."""
        return not self.is_nuclear


@dataclass(frozen=True)
class SurfaceProfile:
    key: str
    name: str
    category: str            # TANKER/PASSAGIER/FRACHT/SONSTIGES/KAMPFSCHIFF
    speed_kn: tuple
    callsigns: tuple
    esm_prob: float          # P(Radar/ESM-Emitter an)
    asm_salvo: tuple         # (min, max) feindliche ASMs pro Salve
    asm_cooldown_s: float
    loiter_nm: float         # Patrouillen-Radius um Basis (nur feindlich)
    spawn_weight: float
    acoustic: TargetSignature
    wiki_url: str | None = None
    default_faction: str | None = None
    rcs_m2: float | None = None


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
    wiki_url: str | None = None
    default_faction: str | None = None
    rcs_m2: float | None = None


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


@dataclass(frozen=True, slots=True)
class ReferenceProfile:
    key: str
    hull_type: str
    length_m: float | None


@dataclass(frozen=True, slots=True)
class AcousticLine:
    frequency_hz: float
    relative_level: float
    width_hz: float


@dataclass(frozen=True, slots=True)
class MachineProfile:
    key: str
    cruise_speed_kn: float
    maximum_speed_kn: float
    quiet_speed_kn: float | None
    propulsion_codes: tuple[str, ...]
    motor_rpm: tuple[float, float] | None
    shaft_rpm: tuple[float, float] | None
    propulsor_type: str
    blade_count: int | None
    cruise_lines: tuple[AcousticLine, ...]
    high_speed_lines: tuple[AcousticLine, ...]
    cruise_broadband: tuple[float, float, float] | None
    high_speed_broadband: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class EnduranceProfile:
    key: str
    battery_capacity_kwh: float
    hotel_load_kw: float
    propulsion_max_kw: float
    propulsion_exponent: float
    generator_power_kw: float
    aip_power_kw: float | None
    aip_energy_kwh: float | None
    reserve_start_fraction: float
    reserve_stop_fraction: float
    snorkel_depth_m: float
    radio_duration_s: float


@dataclass(frozen=True, slots=True)
class SensorProfile:
    key: str
    domain: str
    modes: tuple[str, ...]
    emits: bool
    emitter_key: str | None
    synthetic_range_nm: float | None
    sensitivity_db: float | None
    cadence_s: float
    bearing_uncertainty_deg: float | None
    range_uncertainty_nm: float | None
    depth_uncertainty_m: float | None


@dataclass(frozen=True, slots=True)
class EmitterProfile:
    key: str
    domain: str
    frequency_band_hz: tuple[float, float]
    prf_band_hz: tuple[float, float] | None
    modulation_codes: tuple[str, ...]
    radar_role: str = "surface_search"
    operating_mode: str = "search"
    power_class: str = "medium"
    operating_period_s: float = 10.0
    on_duration_s: float = 10.0


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    key: str
    weapon_type: str
    target_domains: tuple[str, ...]
    runtime_profile_key: str | None
    maximum_speed_kn: float
    engagement_range_nm: tuple[float, float]
    seeker_type: str
    guidance_type: str
    payload_type: str


@dataclass(frozen=True, slots=True)
class LauncherProfile:
    key: str
    launcher_type: str
    mount_count: int
    ready_count: int
    reload_s: float
    arc_center_deg: float
    arc_width_deg: float
    vls_cells: int | None
    weapon_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MagazineProfile:
    key: str
    weapon_key: str
    mission_count: int


@dataclass(frozen=True, slots=True)
class CountermeasureProfile:
    key: str
    effect_type: str
    payload_key: str | None
    mission_count: int
    ready_count: int
    reload_s: float


@dataclass(frozen=True, slots=True)
class ProfileSystems:
    profile_key: str
    reference_key: str | None
    machine_key: str | None
    sensor_keys: tuple[str, ...]
    emitter_keys: tuple[str, ...]
    launcher_keys: tuple[str, ...]
    magazine_keys: tuple[str, ...]
    countermeasure_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogSource:
    id: str
    kind: str
    title: str
    publisher: str | None
    url: str | None
    reference: str
    retrieved: str | None
    license: str | None


@dataclass(frozen=True, slots=True)
class ProvenanceClaim:
    resource: str
    profile_key: str
    field_paths: tuple[str, ...]
    status: str
    source_ids: tuple[str, ...]

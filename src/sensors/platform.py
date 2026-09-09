"""Deterministic platform sensor controllers and observation-only datalink."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import asdict, dataclass

from src.core import config


SIDES = ("friendly", "neutral", "hostile")
DOCTRINES = (
    "submarine",
    "surface_transit",
    "surface_combatant",
    "civil_flight",
    "military_patrol",
)
MAX_LOCAL_TRACKS = 64
MAX_DATALINK_TRACKS = 64


def _stable_int(*parts: object) -> int:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


@dataclass(frozen=True, slots=True)
class PlatformObservation:
    """A detached measurement suitable for AI, saves, and datalink transport."""

    track_id: str
    domain: str
    source: str
    observer_x: float
    observer_y: float
    bearing: float
    range_nm: float | None
    x: float | None
    y: float | None
    course: float | None
    speed_kn: float | None
    depth_m: float | None
    quality: float
    signal: float
    last_seen: float
    bearing_uncertainty_deg: float | None
    range_uncertainty_nm: float | None
    depth_uncertainty_m: float | None
    label: str | None
    fix_source: str | None = None


class ObservationPicture:
    """A strictly bounded collection with deterministic overflow eviction."""

    def __init__(self, stale_s: float, maximum: int):
        self.stale_s = float(stale_s)
        self.maximum = int(maximum)
        self._tracks: dict[str, PlatformObservation] = {}

    def observe(self, observation: PlatformObservation) -> None:
        self._tracks[observation.track_id] = observation
        if len(self._tracks) > self.maximum:
            evict = min(
                self._tracks.values(),
                key=lambda track: (track.last_seen, track.quality, track.track_id),
            )
            del self._tracks[evict.track_id]

    def expire(self, now: float) -> None:
        self._tracks = {
            key: track for key, track in self._tracks.items()
            if now - track.last_seen <= self.stale_s
        }

    def tracks(self, now: float, domains: tuple[str, ...] | None = None
               ) -> tuple[PlatformObservation, ...]:
        tracks = [track for track in self._tracks.values()
                  if now - track.last_seen <= self.stale_s]
        if domains is not None:
            tracks = [track for track in tracks if track.domain in domains]
        return tuple(sorted(tracks, key=lambda track: track.track_id))

    def serialize(self) -> list[dict]:
        return [asdict(track) for track in sorted(
            self._tracks.values(), key=lambda track: track.track_id)]

    def restore(self, rows: list[dict], now: float) -> None:
        if not isinstance(rows, list) or len(rows) > self.maximum:
            raise ValueError("platform picture exceeds track limit")
        tracks: dict[str, PlatformObservation] = {}
        fields = set(PlatformObservation.__dataclass_fields__)
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("invalid platform observation fields")
            track = PlatformObservation(**row)
            _validate_observation(track, now)
            if track.track_id in tracks:
                raise ValueError("duplicate platform observation")
            tracks[track.track_id] = track
        self._tracks = tracks


@dataclass(slots=True)
class SensorController:
    sensor_key: str
    domain: str
    cadence_s: float
    enabled: bool
    next_scan_s: float
    scan_index: int = 0

    def consume_due(self, now: float) -> tuple[int, float] | None:
        if now + 1e-9 < self.next_scan_s:
            return None
        count = int(math.floor((now - self.next_scan_s + 1e-9)
                               / self.cadence_s)) + 1
        index = self.scan_index + count - 1
        scan_time = min(now, self.next_scan_s + (count - 1) * self.cadence_s)
        self.scan_index += count
        self.next_scan_s += count * self.cadence_s
        return index, scan_time


@dataclass(frozen=True, slots=True)
class MotionLimits:
    cruise_speed_kn: float
    maximum_speed_kn: float
    quiet_speed_kn: float | None
    turn_rate_deg_s: float
    acceleration_kn_s: float
    depth_rate_m_s: float


class PlatformSensorSuite:
    """Per-platform component state, local sensor image, and datalink image."""

    def __init__(self, catalog, profile_key: str, sensor_seed: int, *,
                 side: str, doctrine: str, now: float = 0.0,
                 datalink_group: str | None = None):
        if side not in SIDES or doctrine not in DOCTRINES:
            raise ValueError("invalid platform doctrine")
        self.side = side
        self.doctrine = doctrine
        self.datalink_group = datalink_group
        self.sensor_seed = int(sensor_seed)
        self.last_consumed_s = -1.0
        self.controllers: dict[str, SensorController] = {}
        systems = catalog.profile_systems.get(profile_key)
        for key in (() if systems is None else systems.sensor_keys):
            profile = catalog.sensors[key]
            phase = (_stable_int(self.sensor_seed, key, "phase") / 2**64
                     * profile.cadence_s)
            self.controllers[key] = SensorController(
                key, profile.domain, profile.cadence_s, True,
                float(now) + phase)
        self.local_picture = ObservationPicture(30.0, MAX_LOCAL_TRACKS)
        self.datalink_picture = ObservationPicture(30.0, MAX_DATALINK_TRACKS)

    @property
    def datalink_id(self) -> str:
        return f"P{_stable_int(self.sensor_seed, 'datalink'):016x}"

    def update(self, now: float, owner, candidates, world, catalog, *,
               emcon: dict[str, bool] | None = None,
               unavailable: set[str] | None = None,
               degraded: set[str] | None = None) -> None:
        emcon = emcon or {}
        unavailable = unavailable or set()
        degraded = degraded or set()
        self.local_picture.expire(now)
        for key in sorted(self.controllers):
            controller = self.controllers[key]
            due = controller.consume_due(now)
            if due is None or not controller.enabled:
                continue
            scan_index, scan_time = due
            profile = catalog.sensors[key]
            if profile.domain in unavailable:
                continue
            if profile.emits and not emcon.get(profile.domain, True):
                continue
            scale = 0.5 if profile.domain in degraded else 1.0
            for candidate in candidates:
                self._observe_candidate(scan_time, owner, candidate, world, profile,
                                        scan_index, scale)

    def _observe_candidate(self, now, owner, candidate, world, profile,
                           scan_index: int, availability: float) -> None:
        if candidate is owner or getattr(candidate, "sunk", False) \
                or not getattr(candidate, "active", True):
            return
        dx, dy = candidate.x - owner.x, candidate.y - owner.y
        distance = math.hypot(dx, dy)
        target_domain = getattr(candidate, "sensor_domain", "surface")
        owner_domain = getattr(owner, "sensor_domain", "surface")
        if profile.domain in ("radar", "esm", "ais") and owner_domain == "subsurface":
            return
        if ((profile.domain in ("radar", "esm", "ais")
             and target_domain == "subsurface")
                or (profile.domain == "ais" and target_domain != "surface")
                or (profile.domain == "sonar" and target_domain == "air")):
            return
        maximum = (profile.synthetic_range_nm or 0.0) * availability
        if maximum <= 0.0 or distance > maximum:
            return
        if getattr(world, "land_blocks_line", lambda *args: False)(
                owner.x, owner.y, candidate.x, candidate.y):
            return
        if profile.domain == "esm" and not getattr(candidate, "radar_emitting", False):
            return
        if profile.domain == "ais" and not getattr(candidate, "ais_transmitting", False):
            return
        if profile.domain == "sonar":
            blocked = getattr(world, "sonar_path_blocked", lambda *args: False)
            if blocked(owner.x, owner.y, getattr(owner, "depth", 5.0),
                       candidate.x, candidate.y, getattr(candidate, "depth", 5.0)):
                return
            source_noise = (candidate.noise_level()
                            if hasattr(candidate, "noise_level") else
                            1.0 - getattr(candidate, "quiet_factor", lambda: 0.0)())
            received_signal = max(0.0, source_noise) * max(
                0.0, 1.0 - distance / maximum)
            if received_signal <= 0.01:
                return
        token = _candidate_token(candidate)
        rng = random.Random(_stable_int(
            self.sensor_seed, profile.key, scan_index, token))
        truth_bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
        bearing_sigma = (profile.bearing_uncertainty_deg or 0.0) \
            / max(availability, 0.01)
        bearing = (truth_bearing + rng.gauss(0.0, bearing_sigma)) % 360.0
        measured_range = None
        active_sonar = profile.domain == "sonar" and "active" in profile.modes
        if profile.domain in ("radar", "ais") or active_sonar:
            range_sigma = (profile.range_uncertainty_nm or 0.0) \
                / max(availability, 0.01)
            measured_range = max(0.0, distance + rng.gauss(0.0, range_sigma))
        x = y = None
        if measured_range is not None:
            x = owner.x + measured_range * math.sin(math.radians(bearing))
            y = owner.y - measured_range * math.cos(math.radians(bearing))
        depth = None
        if profile.depth_uncertainty_m is not None and "active" in profile.modes:
            depth = max(0.0, getattr(candidate, "depth", 0.0) + rng.gauss(
                0.0, profile.depth_uncertainty_m / max(availability, 0.01)))
        opaque = _stable_int(self.sensor_seed, profile.key, token)
        label = getattr(candidate, "name", None) if profile.domain == "ais" else None
        quality = (config.clamp(received_signal, 0.05, 1.0)
                   if profile.domain == "sonar" else
                   config.clamp(1.0 - distance / maximum, 0.05, 1.0))
        self.local_picture.observe(PlatformObservation(
            track_id=f"L{opaque:016x}", domain=profile.domain,
            source=profile.domain.upper(), observer_x=owner.x,
            observer_y=owner.y, bearing=bearing,
            range_nm=measured_range, x=x, y=y,
            course=(getattr(candidate, "course", None)
                    if profile.domain == "ais" else None),
            speed_kn=(getattr(candidate, "speed", None)
                      if profile.domain == "ais" else None),
            depth_m=depth, quality=quality,
            signal=(config.clamp(received_signal, 0.0, 2.0)
                    if profile.domain == "sonar" else quality),
            last_seen=now,
            bearing_uncertainty_deg=(bearing_sigma or None),
            range_uncertainty_nm=(profile.range_uncertainty_nm
                                  if measured_range is not None else None),
            depth_uncertainty_m=profile.depth_uncertainty_m,
            label=label,
            fix_source=("ACTIVE" if active_sonar else
                        profile.domain.upper() if measured_range is not None else None)))

    def tactical_tracks(self, now: float) -> tuple[PlatformObservation, ...]:
        return tuple(sorted(
            self.local_picture.tracks(now) + self.datalink_picture.tracks(now),
            key=lambda track: (track.last_seen, track.quality, track.track_id),
            reverse=True))

    def tracks_for_candidate(self, candidate, now: float
                             ) -> tuple[PlatformObservation, ...]:
        token = _candidate_token(candidate)
        ids = {
            f"L{_stable_int(self.sensor_seed, key, token):016x}"
            for key in self.controllers
        }
        return tuple(track for track in self.local_picture.tracks(now)
                     if track.track_id in ids)

    def serialize(self) -> dict:
        return {
            "side": self.side,
            "doctrine": self.doctrine,
            "datalink_group": self.datalink_group,
            "last_consumed_s": self.last_consumed_s,
            "controllers": {
                key: {
                    "enabled": value.enabled,
                    "next_scan_s": value.next_scan_s,
                    "scan_index": value.scan_index,
                }
                for key, value in sorted(self.controllers.items())
            },
            "local_picture": self.local_picture.serialize(),
            "datalink_picture": self.datalink_picture.serialize(),
        }

    def restore(self, state: dict, catalog, profile_key: str, now: float) -> None:
        _validate_suite_state(state, catalog, profile_key, now)
        self.side = state["side"]
        self.doctrine = state["doctrine"]
        self.datalink_group = state["datalink_group"]
        self.last_consumed_s = float(state["last_consumed_s"])
        for key, value in state["controllers"].items():
            controller = self.controllers[key]
            controller.enabled = value["enabled"]
            controller.next_scan_s = float(value["next_scan_s"])
            controller.scan_index = value["scan_index"]
        self.local_picture.restore(state["local_picture"], now)
        self.datalink_picture.restore(state["datalink_picture"], now)


def exchange_friendly_datalink(
        suites: list[PlatformSensorSuite], now: float,
        allowed_track_ids: dict[str, set[str]] | None = None) -> None:
    """Publish detached observations after every sender has completed its scan."""
    eligible = sorted(
        (suite for suite in suites
         if suite.side == "friendly" and suite.datalink_group is not None),
        key=lambda suite: suite.datalink_id)
    reports = {
        suite.datalink_id: tuple(
            track for track in suite.local_picture.tracks(now)
            if (allowed_track_ids is None
                or track.track_id in allowed_track_ids.get(suite.datalink_id, set())))
        for suite in eligible
    }
    for receiver in eligible:
        receiver.datalink_picture.expire(now)
        for sender in eligible:
            if sender is receiver or sender.datalink_group != receiver.datalink_group:
                continue
            for report in reports[sender.datalink_id]:
                track_id = f"D{_stable_int(sender.datalink_id, report.track_id):016x}"
                receiver.datalink_picture.observe(PlatformObservation(
                    track_id=track_id, domain=report.domain, source="DATALINK",
                    observer_x=report.observer_x, observer_y=report.observer_y,
                    bearing=report.bearing, range_nm=report.range_nm,
                    x=report.x, y=report.y, course=report.course,
                    speed_kn=report.speed_kn, depth_m=report.depth_m,
                    quality=report.quality, signal=report.signal,
                    last_seen=report.last_seen,
                    bearing_uncertainty_deg=report.bearing_uncertainty_deg,
                    range_uncertainty_nm=report.range_uncertainty_nm,
                    depth_uncertainty_m=report.depth_uncertainty_m,
                    label=report.label, fix_source=report.fix_source))


def motion_limits(catalog, profile_key: str, *, cruise_speed: float,
                  maximum_speed: float, turn_rate: float,
                  acceleration: float, depth_rate: float = 0.5) -> MotionLimits:
    systems = catalog.profile_systems.get(profile_key)
    if systems is None or systems.machine_key is None:
        return MotionLimits(cruise_speed, maximum_speed, None, turn_rate,
                            acceleration, depth_rate)
    machine = catalog.machines[systems.machine_key]
    reference = (catalog.references.get(systems.reference_key)
                 if systems.reference_key is not None else None)
    length = reference.length_m if reference is not None else None
    profiled_turn = (config.clamp(80.0 / length, 0.25, 1.5)
                     if length is not None else turn_rate)
    profiled_acceleration = (config.clamp(5.0 / length, 0.02, 0.08)
                             if length is not None else acceleration)
    profiled_depth = (config.clamp(60.0 / length, 0.35, 0.8)
                      if length is not None and reference.hull_type == "submarine"
                      else depth_rate)
    return MotionLimits(
        machine.cruise_speed_kn, machine.maximum_speed_kn,
        machine.quiet_speed_kn, profiled_turn, profiled_acceleration,
        profiled_depth)


def machine_acoustics(catalog, profile_key: str, speed_kn: float):
    systems = catalog.profile_systems.get(profile_key)
    if systems is None or systems.machine_key is None:
        return None
    machine = catalog.machines[systems.machine_key]
    span = max(0.01, machine.maximum_speed_kn - machine.cruise_speed_kn)
    blend = config.clamp((speed_kn - machine.cruise_speed_kn) / span, 0.0, 1.0)
    count = min(len(machine.cruise_lines), len(machine.high_speed_lines))
    lines = tuple((
        machine.cruise_lines[index].frequency_hz
        + (machine.high_speed_lines[index].frequency_hz
           - machine.cruise_lines[index].frequency_hz) * blend,
        machine.cruise_lines[index].relative_level
        + (machine.high_speed_lines[index].relative_level
           - machine.cruise_lines[index].relative_level) * blend,
        machine.cruise_lines[index].width_hz
        + (machine.high_speed_lines[index].width_hz
           - machine.cruise_lines[index].width_hz) * blend,
    ) for index in range(count))
    broadband = machine.cruise_broadband
    if machine.high_speed_broadband is not None and broadband is not None:
        broadband = tuple(
            broadband[index] + (machine.high_speed_broadband[index]
                                 - broadband[index]) * blend
            for index in range(3))
    return lines, broadband


def snapshot_observation(owner, target, *, domain: str, now: float = 0.0,
                         positioned: bool = True) -> PlatformObservation:
    """Detach the legacy non-pilot sensor result before AI can consume it."""
    dx, dy = target.x - owner.x, target.y - owner.y
    distance = math.hypot(dx, dy)
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    signal = config.clamp(getattr(target, "noise_level", lambda: 1.0)(), 0.0, 2.0)
    return PlatformObservation(
        track_id="LEGACY", domain=domain, source=domain.upper(), bearing=bearing,
        observer_x=owner.x, observer_y=owner.y,
        range_nm=distance if positioned else None,
        x=target.x if positioned else None, y=target.y if positioned else None,
        course=getattr(target, "course", None) if positioned else None,
        speed_kn=getattr(target, "speed", None) if positioned else None,
        depth_m=getattr(target, "depth", None) if domain == "sonar" else None,
        quality=1.0, signal=signal, last_seen=now,
        bearing_uncertainty_deg=None, range_uncertainty_nm=None,
        depth_uncertainty_m=None, label=None,
        fix_source="ACTIVE" if domain == "sonar" and positioned else None)


def _validate_observation(track: PlatformObservation, now: float) -> None:
    if (not isinstance(track.track_id, str) or not 1 <= len(track.track_id) <= 64
            or track.domain not in ("radar", "esm", "sonar", "ais")
            or track.source not in ("RADAR", "ESM", "SONAR", "AIS", "DATALINK")
            or track.fix_source not in (None, "ACTIVE", "TMA", "BUOY", "FUSED",
                                        "RADAR", "AIS")
            or not _finite_between(track.bearing, 0.0, 360.0, upper_open=True)
            or not _finite_between(track.quality, 0.0, 1.0)
            or not _finite_between(track.signal, 0.0, 2.0)
            or not _finite_between(track.last_seen, 0.0, now)
            or (track.label is not None and (not isinstance(track.label, str)
                                              or len(track.label) > 80))):
        raise ValueError("invalid platform observation")
    if (not _finite_between(track.observer_x, -1e6, 1e6)
            or not _finite_between(track.observer_y, -1e6, 1e6)):
        raise ValueError("invalid platform observation origin")
    for value, high in ((track.range_nm, 10_000.0), (track.speed_kn, 5_000.0),
                        (track.depth_m, 10_000.0),
                        (track.bearing_uncertainty_deg, 180.0),
                        (track.range_uncertainty_nm, 10_000.0),
                        (track.depth_uncertainty_m, 10_000.0)):
        if value is not None and not _finite_between(value, 0.0, high):
            raise ValueError("invalid platform observation value")
    if (track.x is None) != (track.y is None) or (track.range_nm is None) != (track.x is None):
        raise ValueError("invalid platform observation position")
    if track.x is not None and (not _finite_between(track.x, -1e6, 1e6)
                                or not _finite_between(track.y, -1e6, 1e6)):
        raise ValueError("invalid platform observation position")
    if track.course is not None and not _finite_between(
            track.course, 0.0, 360.0, upper_open=True):
        raise ValueError("invalid platform observation course")


def _validate_suite_state(state: dict, catalog, profile_key: str, now: float) -> None:
    expected = {"side", "doctrine", "datalink_group", "last_consumed_s", "controllers",
                "local_picture", "datalink_picture"}
    if not isinstance(state, dict) or set(state) != expected:
        raise ValueError("invalid platform sensor state")
    if state["side"] not in SIDES or state["doctrine"] not in DOCTRINES:
        raise ValueError("invalid platform doctrine")
    group = state["datalink_group"]
    if group is not None and (not isinstance(group, str) or not 1 <= len(group) <= 64):
        raise ValueError("invalid datalink group")
    if not _finite_between(state["last_consumed_s"], -1.0, now):
        raise ValueError("invalid consumed observation time")
    systems = catalog.profile_systems.get(profile_key)
    expected_sensors = set(() if systems is None else systems.sensor_keys)
    controllers = state["controllers"]
    if not isinstance(controllers, dict) or set(controllers) != expected_sensors:
        raise ValueError("invalid sensor controller set")
    for key, controller in controllers.items():
        cadence = catalog.sensors[key].cadence_s
        if (not isinstance(controller, dict)
                or set(controller) != {"enabled", "next_scan_s", "scan_index"}
                or type(controller["enabled"]) is not bool
                or type(controller["scan_index"]) is not int
                or not 0 <= controller["scan_index"] <= 2**63 - 1
                or not _finite_between(controller["next_scan_s"], 0.0,
                                       now + cadence)
                or controller["next_scan_s"] < max(0.0, now - cadence)):
            raise ValueError("invalid sensor controller state")
        if controller["next_scan_s"] <= now + 1e-9:
            due = int(math.floor(
                (now - controller["next_scan_s"] + 1e-9) / cadence)) + 1
            if controller["scan_index"] + due > 2**63 - 1:
                raise ValueError("invalid sensor controller sequence")
    for rows, maximum in ((state["local_picture"], MAX_LOCAL_TRACKS),
                          (state["datalink_picture"], MAX_DATALINK_TRACKS)):
        picture = ObservationPicture(30.0, maximum)
        picture.restore(rows, now)


def validate_suite_state(state: dict, catalog, profile_key: str, now: float) -> bool:
    try:
        _validate_suite_state(state, catalog, profile_key, now)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _finite_between(value, low: float, high: float, upper_open: bool = False) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value
            and (value < high if upper_open else value <= high))


def _candidate_token(candidate) -> str:
    return (f"{type(candidate).__name__}:"
            f"{getattr(candidate, 'id', getattr(candidate, 'seq', 0))}")

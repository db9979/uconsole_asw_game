"""Sonar contacts and the towed-array handling states.

``Contact`` (a sonar contact: bearing-only when passive, positioned by ping,
TMA or another dated fix) and ``TowState``, moved verbatim from
``sonar.py``, which re-exports them with ``FIX_SOURCES``.
"""

import math
from enum import Enum

from src.core import config


# Independent fix sources a contact retains (one dated fix each).
FIX_SOURCES = ("PING", "DIPPING", "TMA", "SONOBUOY", "MAD", "VISUAL", "CONSORT")
# Sources whose fix ages out like a ping (the others like a passive track).
POINT_FIX_SOURCES = ("PING", "DIPPING", "MAD", "VISUAL", "CONSORT")


class TowState(str, Enum):
    STOWED = "STOWED"
    DEPLOYING = "DEPLOYING"
    STREAMED = "STREAMED"
    RETRIEVING = "RETRIEVING"
    FAULT = "FAULT"


class Contact:
    """Sonarkontakt: passiv nur Peilung, Position via Ping oder TMA.

    Klassifizierung erfolgt manuell (player_class) auf Basis der
    hörbaren Geräusch-Signatur (signature).
    """

    def __init__(self, contact_id: int, target_id: int, origin: str, kind: str):
        self.id = contact_id
        self.target_id = target_id
        self.origin = origin   # "passiv" | "ping"
        self.kind = kind       # "sub"|"animal"|"surface"|"decoy"|"torpedo"
        self.bearing = 0.0
        self.passive_bearing = None
        self.raw_bearing = None
        self.raw_bearings = []
        self.bearing_uncertainty_deg = None
        self.range_est = None  # None = nicht geortet (nur Peilung)
        self.range_sigma_nm = None  # 1-sigma Unsicherheit der Entfernung
        self.range_source = None  # None | "ping" | "tma"
        self.range_seen = None
        self.confidence = 0.0
        self.quality = 0.0
        self.last_seen = 0.0
        self.depth_est = None
        self.depth_sigma_m = None  # 1-sigma Unsicherheit der Tiefe
        self.player_class = None  # None|U_BOOT|KAMPFSCHIFF|BIOLOGISCH|FAHRZEUG|FLUGZEUG
        # Operator's catalog assignment (profile key from the contact
        # analyser); an annotation like player_class, never inferred.
        self.player_profile = None
        self.released_to_opz = False
        self.passive_source = "SONAR-BRG"
        self.observer_x = 0.0
        self.observer_y = 0.0
        self.signature = ""       # zuletzt gehörte Geräusch-Signatur
        # W1: SNR + TMA
        self.snr = -99.0          # dB, -99 = gerade nicht detektiert
        self.tma_pos = None       # (x, y) NM
        self.tma_course = None
        self.tma_speed = None
        self.tma_quality = 0.0
        self.tma_ellipse = None   # (major NM, minor NM, orientation deg)
        # Towed-array left/right ambiguity: the line array cannot tell a
        # bearing from its mirror about the array axis until resolved.
        self.towed_ambiguous = False
        self.ambiguity_axis = None     # tow heading when the ambiguity began
        self.mirror_bearing = None
        self.tonal_hz = None           # measured (Doppler-shifted) tonal
        self.towed_resolved = False
        # Operator's choice of array side for a towed-only contact
        # ("STBD" or "PORT"); the display follows it until resolved.
        self.towed_side = "STBD"
        self.tma_seen = None
        self.buoy_fixes = []  # raw (t, x, y, quality), not ownship passive bearings
        self.buoy_reports = {}  # buoy sequence -> detached measured report
        self.helo_qualified = False
        self.buoy_released_to_opz = False
        self.fixes = {}
        self.ping_pos = None
        self.observed_x = None
        self.observed_y = None
        self._passive_epoch = None
        self._bearing_filter_t = None
        self._bearing_filter_rate_deg_s = 0.0
        self._bearing_filter_uncertainty_deg = None
        self._fx = 0.0
        self._fy = 0.0
        self.array_observations = {}
        self.fusion_status = "KEINE DATEN"
        self.fusion_delta_deg = None
        self.fused_quality = 0.0
        # W2: independent helicopter dip-passive bearing track. Kept fully
        # separate from the ship's own passive_bearing/_fx/_fy/observer_x/y -
        # they are measured from different platforms and must never corrupt
        # each other's filter state (the reported bug: the frigate's own
        # bearing was being overwritten every tick the helo was also dipping).
        self.dip_bearing = None
        self.dip_bearing_uncertainty_deg = None
        self.dip_last_seen = None
        self.dip_observer_x = None
        self.dip_observer_y = None
        self.dip_released_to_opz = False
        self.ship_observer_x = None
        self.ship_observer_y = None

    def update_passive(self, bearing: float, confidence: float,
                       quality: float, signature: str, t: float,
                       snr: float = 0.0,
                       bearing_uncertainty_deg: float = None):
        """Passives Hören: nur (fehlerbehaftete) Peilung."""
        raw = bearing % 360.0
        self.raw_bearing = raw
        epoch = math.floor((t + 1e-9) / config.SONAR_BEARING_NOISE_EPOCH_S)
        uncertainty = (max(0.25, (1.0 - quality) * config.BEARING_ERR_BOW_DEG)
                       if bearing_uncertainty_deg is None
                       else max(0.05, bearing_uncertainty_deg))
        if epoch != self._passive_epoch:
            self.raw_bearings.append((t, raw, uncertainty))
            del self.raw_bearings[:-config.BEARING_TRACK_MAX_PTS]
            self._passive_epoch = epoch
        if self.passive_bearing is None:
            self.passive_bearing = raw
            self._bearing_filter_uncertainty_deg = uncertainty
            self._bearing_filter_t = t
            self._bearing_filter_rate_deg_s = 0.0
        elif self._bearing_filter_t is None:
            # Legacy saves have a presentation bearing but no causal rate state.
            self._bearing_filter_t = t
            self._bearing_filter_rate_deg_s = 0.0
            if self._bearing_filter_uncertainty_deg is None:
                self._bearing_filter_uncertainty_deg = (
                    self.bearing_uncertainty_deg or uncertainty)
        elif t > self._bearing_filter_t:
            dt = t - self._bearing_filter_t
            alpha = 1.0 - math.exp(-dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            beta = alpha * alpha / max(1e-6, 2.0 - alpha)
            self._bearing_filter_rate_deg_s *= math.exp(
                -dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            predicted = (self.passive_bearing
                         + self._bearing_filter_rate_deg_s * dt) % 360.0
            innovation = config.angle_diff_deg(raw, predicted)
            self.passive_bearing = (predicted + alpha * innovation) % 360.0
            self._bearing_filter_rate_deg_s = config.clamp(
                self._bearing_filter_rate_deg_s + beta * innovation / dt,
                -config.SONAR_BEARING_RATE_MAX_DEG_S,
                config.SONAR_BEARING_RATE_MAX_DEG_S)
            prior_uncertainty = max(
                0.05, self._bearing_filter_uncertainty_deg or uncertainty)
            self._bearing_filter_uncertainty_deg = math.sqrt(
                (1.0 - alpha) * prior_uncertainty * prior_uncertainty
                + alpha * (uncertainty * uncertainty
                           + (1.0 - alpha) * innovation * innovation))
            self._bearing_filter_t = t
        self.confidence = min(1.0, confidence)
        self.quality = min(1.0, quality)
        self.last_seen = t
        self.snr = snr
        self.expire_ping_fix(t)
        if self.range_source == "ping" and self.ping_pos is None \
                and self.range_est is not None:
            # Legacy saves did not retain the Cartesian active fix.
            self.ping_pos = (
                self._fx + self.range_est * math.sin(math.radians(self.bearing)),
                self._fy - self.range_est * math.cos(math.radians(self.bearing)))
        if self.range_source == "ping" and self.ping_pos is not None:
            self.observed_x, self.observed_y = self.ping_pos
        elif self.range_source == "tma" and self.tma_pos is not None:
            self.observed_x, self.observed_y = self.tma_position_at(t)
        if self.observed_x is not None and self.observed_y is not None:
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
        elif self.range_source not in ("ping", "tma", "buoy"):
            self.bearing = self.passive_bearing
            self.bearing_uncertainty_deg = self._bearing_filter_uncertainty_deg
        if signature:
            self.signature = signature

    def update_dip_passive(self, bearing: float, t: float, observer_x: float,
                           observer_y: float,
                           bearing_uncertainty_deg: float) -> None:
        """W2: the helicopter's own dipping-sonar bearing track.

        A lighter smoothing filter than update_passive() - dips are
        occasional, hover-based fixes, not a continuous towed/bow array -
        but it is fully independent state so it never overwrites the ship's
        own passive_bearing/observer position."""
        raw = bearing % 360.0
        if self.dip_bearing is None or self.dip_last_seen is None:
            self.dip_bearing = raw
        else:
            dt = max(0.0, t - self.dip_last_seen)
            alpha = 1.0 - math.exp(-dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            self.dip_bearing = (self.dip_bearing + alpha * config.angle_diff_deg(
                raw, self.dip_bearing)) % 360.0
        self.dip_bearing_uncertainty_deg = max(0.05, bearing_uncertainty_deg)
        self.dip_observer_x, self.dip_observer_y = observer_x, observer_y
        self.dip_last_seen = t

    def _publish_fix(self, source: str, measured_at: float, fixed_at: float,
                     x: float, y: float, uncertainty_nm: float,
                     quality: float, depth_m=None, depth_uncertainty_m=None):
        """Retain one detached, measurement-dated fix per independent source."""
        self.fixes[source] = dict(
            source=source, measured_at=float(measured_at), fixed_at=float(fixed_at),
            x=float(x), y=float(y), uncertainty_nm=float(uncertainty_nm),
            depth_m=None if depth_m is None else float(depth_m),
            depth_uncertainty_m=(None if depth_uncertainty_m is None
                                 else float(depth_uncertainty_m)),
            quality=float(config.clamp(quality, 0.0, 1.0)))

    def active_fixes(self, now: float) -> tuple:
        """Return stable detached fix copies whose measurements remain current."""
        result = []
        for source in FIX_SOURCES:
            fix = self.fixes.get(source)
            lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                        if source in POINT_FIX_SOURCES
                        else config.SONAR_CONTACT_LOST_S)
            if (fix is not None and 0.0 <= now - fix["measured_at"] <= lifetime):
                result.append(dict(fix))
        return tuple(result)

    def update_ping(self, bearing: float, range_est: float, depth_est: float,
                     confidence: float, t: float, snr: float = 0.0,
                     range_sigma_nm: float = None, depth_sigma_m: float = None,
                     fixed_at: float = None, fix_source: str = "PING"):
        """Aktiver Ping: liefert Position + Tiefe (maßstabsgenau)."""
        self.bearing = bearing % 360.0
        self.raw_bearing = self.bearing
        self.bearing_uncertainty_deg = 1.5 / math.sqrt(3)
        self.range_est = range_est
        self.range_sigma_nm = (config.SONAR_PING_RANGE_ERROR_NM / math.sqrt(3)
                               if range_sigma_nm is None else max(1e-6, range_sigma_nm))
        self.range_source = "ping"
        self.range_seen = t
        self.depth_est = depth_est
        self.depth_sigma_m = (config.SONAR_PING_DEPTH_ERROR_M / math.sqrt(3)
                              if depth_sigma_m is None else max(1e-6, depth_sigma_m))
        self.origin = "ping"
        self.confidence = min(1.0, confidence)
        self.quality = 1.0
        self.last_seen = t
        self.snr = snr
        self.ping_pos = (
            self._fx + range_est * math.sin(math.radians(self.bearing)),
            self._fy - range_est * math.cos(math.radians(self.bearing)))
        self.observed_x, self.observed_y = self.ping_pos
        self._publish_fix(
            fix_source, t, t if fixed_at is None else fixed_at, *self.ping_pos,
            self.range_sigma_nm, self.quality, self.depth_est, self.depth_sigma_m)

    def expire_ping_fix(self, t: float) -> None:
        """Expire evidence even without detections (name retained for callers).

        TMA/buoy positions and TMA motion are usable for at most
        SONAR_CONTACT_LOST_S since their measurement, not last passive hearing.
        The uncertainty fields for these estimates are heuristic, not covariance.
        """
        for source in tuple(self.fixes):
            lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                        if source in POINT_FIX_SOURCES
                        else config.SONAR_CONTACT_LOST_S)
            measured_at = self.fixes[source].get("measured_at")
            if measured_at is None or t - measured_at > lifetime:
                del self.fixes[source]
        tma_seen = self.tma_seen
        if tma_seen is None and self.range_source == "tma":
            tma_seen = self.range_seen  # pre-evidence saves
        if (self.tma_pos is not None or self.tma_course is not None
                or self.tma_speed is not None) and (tma_seen is None or
                t - tma_seen > config.SONAR_CONTACT_LOST_S):
            self.tma_pos = self.tma_course = self.tma_speed = None
            self.tma_ellipse = None
            self.tma_quality = 0.0
            self.tma_seen = None
        max_age = (config.SONAR_PING_FIX_MAX_AGE_S
                   if self.range_source == "ping" else config.SONAR_CONTACT_LOST_S)
        if self.range_source is not None and (self.range_seen is None
                or t - self.range_seen > max_age):
            self.range_est = None
            self.range_sigma_nm = None
            self.range_source = None
            self.depth_est = None
            self.depth_sigma_m = None
            self.observed_x = self.observed_y = None
            self.ping_pos = None
            if self.passive_bearing is not None:
                self.bearing = self.passive_bearing
                self.bearing_uncertainty_deg = \
                    self._bearing_filter_uncertainty_deg
        self.array_observations = {
            key: value for key, value in self.array_observations.items()
            if t - value["last_seen"] <= 4.0}
        if len(self.array_observations) < 2:
            ambiguous_status = (self.fusion_status if str(self.fusion_status)
                                .startswith("TAS L/R?") else "TAS L/R?")
            self.fusion_status = (ambiguous_status if self.towed_ambiguous
                                  and set(self.array_observations) == {"TOWED"}
                                  else "NUR " + next(iter(self.array_observations))
                                  if self.array_observations else "KEINE DATEN")
            self.fusion_delta_deg = None
            self.fused_quality = max((report["quality"] for report in
                                      self.array_observations.values()), default=0.0)

    def update_buoy(self, x: float, y: float, quality: float, t: float):
        """Keep raw cross-fixes separate; smooth only the public position.

        Fresh ping > fresh buoy > TMA avoids source flapping. The filter is a
        bounded convex blend, with no velocity extrapolation or covariance claim.
        """
        self.expire_ping_fix(t)
        if not self.buoy_fixes or int(t // 2) != int(self.buoy_fixes[-1][0] // 2):
            self.buoy_fixes.append((t, x, y, quality))
            del self.buoy_fixes[:-config.BEARING_TRACK_MAX_PTS]
        buoy_uncertainty = max(.5, (1.0 - quality) * 8.0)
        self._publish_fix("SONOBUOY", t, t, x, y, buoy_uncertainty, quality)
        if self.range_source == "ping":
            return
        if (self.range_source == "buoy" and self.observed_x is not None
                and self.observed_y is not None and self.range_seen is not None):
            alpha = 1.0 - math.exp(-max(0.0, t - self.range_seen)
                                   / config.SONAR_BEARING_DISPLAY_TAU_S)
            x = self.observed_x + alpha * (x - self.observed_x)
            y = self.observed_y + alpha * (y - self.observed_y)
        self.observed_x, self.observed_y = x, y
        self.bearing = math.degrees(math.atan2(x - self._fx, -(y - self._fy))) % 360
        self.range_est = math.hypot(x - self._fx, y - self._fy)
        self.range_sigma_nm = buoy_uncertainty
        self.bearing_uncertainty_deg = None
        self.depth_est = self.depth_sigma_m = None
        self.range_source = "buoy"
        self.range_seen = t
        self.origin = "bojenkreuzpeilung"

    def update_mad(self, x: float, y: float, t: float, uncertainty_nm: float,
                   quality: float):
        """A MAD pass over the hull: a dated position fix without depth,
        course or speed. A fresh ping keeps precedence over it."""
        self.expire_ping_fix(t)
        self._publish_fix("MAD", t, t, x, y, uncertainty_nm, quality)
        self.confidence = min(1.0, max(self.confidence, quality))
        self.quality = max(self.quality, quality)
        self.last_seen = t
        if self.range_source == "ping":
            return
        self.observed_x, self.observed_y = x, y
        self.bearing = math.degrees(math.atan2(x - self._fx, -(y - self._fy))) % 360
        self.range_est = math.hypot(x - self._fx, y - self._fy)
        self.range_sigma_nm = uncertainty_nm
        self.bearing_uncertainty_deg = None
        self.depth_est = self.depth_sigma_m = None
        self.range_source = "mad"
        self.range_seen = t
        self.origin = "mad"

    def update_consort(self, x: float, y: float, t: float, uncertainty_nm: float,
                       quality: float, depth_m=None, depth_uncertainty_m=None):
        """A fix from the consort over the datalink: its active echo, or its
        passive bearing crossed with the frigate's. A fresh own ping keeps
        precedence over it."""
        self.expire_ping_fix(t)
        self._publish_fix("CONSORT", t, t, x, y, uncertainty_nm, quality,
                          depth_m, depth_uncertainty_m)
        self.confidence = min(1.0, max(self.confidence, quality))
        self.quality = max(self.quality, quality)
        self.last_seen = max(self.last_seen, t)
        if self.range_source == "ping":
            return
        self.observed_x, self.observed_y = x, y
        self.bearing = math.degrees(math.atan2(x - self._fx, -(y - self._fy))) % 360
        self.range_est = math.hypot(x - self._fx, y - self._fy)
        self.range_sigma_nm = uncertainty_nm
        self.bearing_uncertainty_deg = None
        self.depth_est = depth_m
        self.depth_sigma_m = depth_uncertainty_m
        self.range_source = "consort"
        self.range_seen = t
        self.origin = "consort"

    def update_visual(self, bearing: float, range_nm: float, t: float,
                      uncertainty_nm: float, quality: float,
                      observer_x: float, observer_y: float):
        """A stadimeter reading through a periscope: a dated position fix
        on the surface from the measured bearing and the estimated range.
        A fresh ping keeps precedence over it."""
        self.expire_ping_fix(t)
        rad = math.radians(bearing % 360.0)
        x = observer_x + range_nm * math.sin(rad)
        y = observer_y - range_nm * math.cos(rad)
        self._publish_fix("VISUAL", t, t, x, y, uncertainty_nm, quality, 0.0, 1.0)
        self.confidence = min(1.0, max(self.confidence, quality))
        self.quality = max(self.quality, quality)
        self.last_seen = t
        if self.range_source == "ping":
            return
        self.observed_x, self.observed_y = x, y
        self.bearing = bearing % 360.0
        self.raw_bearing = self.bearing
        self.range_est = range_nm
        self.range_sigma_nm = uncertainty_nm
        self.bearing_uncertainty_deg = config.UBOOT_SCOPE_BEARING_ERR_DEG
        self.depth_est, self.depth_sigma_m = 0.0, 1.0
        self.range_source = "visual"
        self.range_seen = t
        self.origin = "visual"

    def tma_range_sigma_nm(self, quality: float) -> float:
        """1-sigma position uncertainty: the covariance semi-major axis, never
        more optimistic than the observability-based quality heuristic (the
        linearized covariance is overconfident in poor geometry)."""
        heuristic = max(0.1, (1.0 - quality) * 12.0)
        if self.tma_ellipse is not None:
            return config.clamp(max(self.tma_ellipse[0], heuristic), 0.1, 12.0)
        return heuristic

    def accept_operator_tma(self, pos, course: float, speed: float,
                            quality: float, t: float) -> None:
        """Take the operator's accepted solution as the contact's TMA fix.

        The position is dead-reckoned along course/speed until the fix ages
        out; the operator refines and re-accepts as bearings accumulate.
        """
        self.expire_ping_fix(t)
        self.tma_pos = (float(pos[0]), float(pos[1]))
        self.tma_course = float(course) % 360.0
        self.tma_speed = float(speed)
        self.tma_quality = float(quality)
        self.tma_seen = t
        self.tma_ellipse = None
        sigma = self.tma_range_sigma_nm(quality)
        self._publish_fix("TMA", t, t, self.tma_pos[0], self.tma_pos[1], sigma,
                          self.tma_quality)
        if self.range_source not in ("ping", "buoy"):
            self.observed_x, self.observed_y = self.tma_pos
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
            self.range_sigma_nm = sigma
            self.range_source = "tma"
            self.range_seen = t
            self.bearing_uncertainty_deg = None
            self.depth_est = self.depth_sigma_m = None

    def tma_position_at(self, t: float):
        """The accepted TMA position dead-reckoned to time ``t``."""
        if self.tma_pos is None:
            return None
        if self.tma_seen is None or self.tma_course is None or self.tma_speed is None:
            return self.tma_pos
        step = config.kn_to_nm_per_s(self.tma_speed) * max(0.0, t - self.tma_seen)
        course = math.radians(self.tma_course)
        return (self.tma_pos[0] + step * math.sin(course),
                self.tma_pos[1] - step * math.cos(course))

    def update_tma(self, sol, t: float, fixed_at: float = None):
        """TMA-Estimate übernehmen (nur, solange kein frischerer Ping)."""
        self.expire_ping_fix(t)
        if (self.tma_pos is not None
                and self.tma_quality >= config.TMA_RANGE_MIN_QUALITY
                and sol.quality < config.TMA_RANGE_MIN_QUALITY):
            return
        alpha = config.TMA_PRESENTATION_ALPHA
        if self.tma_pos is None:
            self.tma_pos = tuple(sol.pos)
            self.tma_course = sol.course
            self.tma_speed = sol.speed
            self.tma_quality = sol.quality
        else:
            self.tma_pos = (self.tma_pos[0] + (sol.pos[0] - self.tma_pos[0]) * alpha,
                            self.tma_pos[1] + (sol.pos[1] - self.tma_pos[1]) * alpha)
            if self.tma_course is None:
                self.tma_course = sol.course
            else:
                self.tma_course = (self.tma_course + config.angle_diff_deg(
                    sol.course, self.tma_course) * alpha) % 360.0
            if self.tma_speed is None:
                self.tma_speed = sol.speed
            else:
                self.tma_speed += (sol.speed - self.tma_speed) * alpha
            self.tma_quality += (sol.quality - self.tma_quality) * alpha
        self.tma_seen = t
        self.tma_ellipse = (tuple(float(v) for v in sol.ellipse)
                            if getattr(sol, "ellipse", None) is not None else None)
        sigma = self.tma_range_sigma_nm(sol.quality)
        if sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self._publish_fix("TMA", t, t if fixed_at is None else fixed_at,
                              self.tma_pos[0], self.tma_pos[1], sigma,
                              self.tma_quality)
        if self.range_source not in ("ping", "buoy") and \
                sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self.observed_x, self.observed_y = self.tma_pos
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
            self.range_sigma_nm = sigma
            self.range_source = "tma"
            self.range_seen = t
            self.bearing_uncertainty_deg = None
            self.depth_est = self.depth_sigma_m = None

    def decay(self, dt: float, t: float) -> bool:
        """Konfidenz sinkt ohne neue Detektion; nach Zeit + niedriger
        Konfidenz gilt der Kontakt als verloren (False = entfernen)."""
        self.expire_ping_fix(t)
        self.confidence = max(
            0.0, self.confidence - config.SONAR_CONF_DECAY_PER_S * dt)
        if (t - self.last_seen >= config.SONAR_CONTACT_LOST_S
                and self.confidence <= 0.15):
            return False
        return True

    @property
    def positioned(self) -> bool:
        return self.range_est is not None

    @property
    def display_label(self) -> str:
        return config.PLAYER_CLASS_LABELS.get(self.player_class, "Unbekannt")

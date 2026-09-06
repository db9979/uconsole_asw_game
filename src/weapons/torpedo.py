"""Torpedo-Modell: Start, Drahtführung (Spreiz-Interzeption), Trefferlogik."""

import math

from src.core import config
from src.data.catalog import CATALOG


class Torpedo:
    SPEED_KN = 45.0
    RANGE_NM = 12.0
    KILL_DIST_NM = 0.135   # ~250 m Sprengwirkungsradius
    KILL_DEPTH_M = 15.0    # Tiefentoleranz
    TURN_DEG_PER_S = 8.0
    DEPTH_RATE_M_PER_S = 10.0

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 target_depth_m: float, target_sub, idx: int,
                 kill_dist_nm: float = None, kill_depth_m: float = None,
                 speed_kn: float = None, guidance_x: float = None,
                 guidance_y: float = None):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.depth = 5.0
        self.target_depth = target_depth_m
        self.target = target_sub
        self.idx = idx
        self.travel = 0.0
        self.state = "RUN"  # RUN, HIT, SASE
        self.kill_dist_nm = self.KILL_DIST_NM if kill_dist_nm is None else kill_dist_nm
        self.kill_depth_m = self.KILL_DEPTH_M if kill_depth_m is None else kill_depth_m
        self.speed_kn = self.SPEED_KN if speed_kn is None else speed_kn
        self._search_phase = 0.0     # M15: Serpentin-Phase
        self._midcourse = course_deg % 360.0  # M15: Draht-Mittelkurs
        self._midcourse_timer = 0.0
        self.guidance_x = guidance_x
        self.guidance_y = guidance_y
        self.seeker_acquired = False

    @property
    def speed_nm_per_s(self) -> float:
        """Physikalische Geschwindigkeit in NM pro Simulationssekunde."""
        return config.kn_to_nm_per_s(self.speed_kn)

    def distance_to_target_nm(self) -> float:
        if self.target is None or getattr(self.target, "sunk", False):
            return float("inf")
        return math.hypot(self.target.x - self.x, self.target.y - self.y)

    def guidance_distance_nm(self) -> float:
        """Operator-visible distance to the observed fire-control solution."""
        if self.guidance_x is None or self.guidance_y is None:
            return float("inf")
        return math.hypot(self.guidance_x - self.x, self.guidance_y - self.y)

    def wire_update(self, x_nm: float, y_nm: float) -> None:
        """Feed an observed contact position into the wire guidance loop."""
        if self.state != "RUN" or self.seeker_acquired:
            return
        self.guidance_x, self.guidance_y = x_nm, y_nm
        self._midcourse = math.degrees(
            math.atan2(x_nm - self.x, -(y_nm - self.y))) % 360.0

    def update(self, dt: float) -> None:
        if self.state != "RUN":
            return

        # M15: Drahtgeführte Führung.
        #  - jenseits von TORP_HOME_RANGE_NM: Serpentin-Suchlauf (Zickzack
        #    um den Draht-Kurs) mit Mittelkurs-Update auf die aktuelle
        #    Zielposition;
        #  - innerhalb: Präzisions-Homing mit Interzeptions-Vorlauf.
        sub = self.target
        desired = None
        wobble = 0.0
        turn = self.TURN_DEG_PER_S
        target_alive = (sub is not None and not getattr(sub, "sunk", False)
                        and getattr(sub, "state", None) != "SINKING")
        if target_alive and self.distance_to_target_nm() <= config.TORP_HOME_RANGE_NM:
            self.seeker_acquired = True
        if self.seeker_acquired and target_alive:
            dist = self.distance_to_target_nm()
            desired = math.degrees(
                math.atan2(sub.x - self.x, -(sub.y - self.y))) % 360.0
            turn = 15.0
        else:
            # Vor der Eigenortung folgt der Torpedo nur Drahtdaten und sucht
            # um deren Kurs. Die wahre Zielposition korrigiert ihn hier nicht.
            self._search_phase += dt * 0.03
            desired = (self._midcourse
                       + 15.0 * math.sin(self._search_phase)) % 360.0
            wobble = 8.0 * math.sin(self._search_phase * 0.7)

        # Tiefe ansteuern (im Suchlauf mit Wobble, sonst Zieltiefe).
        # Proportionaler Regelkreis: reicht auch bei kurzen Anflügen,
        # um in Zieltiefe zu treffen (lineares Tauchen kam zu spat an).
        d_target = self.target_depth + wobble
        d_diff = d_target - self.depth
        if abs(d_diff) <= 1.0:
            self.depth = d_target
        else:
            self.depth += config.clamp(
                d_diff, -self.DEPTH_RATE_M_PER_S * dt,
                self.DEPTH_RATE_M_PER_S * dt)

        throttle = 1.0
        if desired is not None:
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -turn * dt, turn * dt)) % 360.0
            # M15: bei starkem Ruderbedarf krabbeln, damit der Torpedo
            # nicht um das Ziel kreist: Kurs erst richten, dann anrennen.
            if abs(diff) > 60.0:
                throttle = 0.6
            else:
                throttle = 1.0 - 0.5 * max(
                    0.0, min(1.0, (abs(diff) - 30.0) / 30.0))
        # Bewegung (Anti-Tunneling: Swept-Check über den ganzen Schritt)
        ox, oy = self.x, self.y
        step = self.speed_nm_per_s * dt * throttle
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step

        if self.travel >= self.RANGE_NM:
            self.state = "SASE"
            return

        # Trefferprüfung (Punkt-Strecke: Zieldistanz entlang der Flugbahn)
        if target_alive:
            dist = self._swept_dist(sub, ox, oy)
            if (dist <= self.kill_dist_nm
                    and abs(self.depth - sub.depth) <= self.kill_depth_m):
                self.state = "HIT"
                sub.hit()

    def _swept_dist(self, sub, ox: float, oy: float) -> float:
        """Min. Distanz Ziel-Position -> Torpedo-Strecke (ox,oy)->(x,y)."""
        fx, fy = self.x - ox, self.y - oy
        l2 = fx * fx + fy * fy
        if l2 < 1e-12:
            return math.hypot(sub.x - self.x, sub.y - self.y)
        t = ((sub.x - ox) * fx + (sub.y - oy) * fy) / l2
        t = config.clamp(t, 0.0, 1.0)
        return math.hypot(ox + t * fx - sub.x, oy + t * fy - sub.y)


class EnemyTorpedo:
    """Feindlicher Torpedo (M5): Vorhaltkurs mit terminaler Eigenortung.

    Ab der Kontakt-DB auch passiv auffindbar: lautes Hochton-Kreischen,
    das im LOFAR mit fallender Frequenz sichtbar wird (Sonarkontakt
    mit kind='torpedo').
    """

    _next_id = 2000000

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 depth_m: float, idx: int):
        self.id = EnemyTorpedo._next_id
        EnemyTorpedo._next_id += 1
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.depth = depth_m
        self.idx = idx
        self.travel = 0.0
        self.state = "RUN"  # RUN, HIT, SASE
        self.torpedo_class = "enemy"
        prof = CATALOG.get_torpedo("enemy_torp")
        self.speed_kn = (prof.speed_kn if prof is not None
                         else config.ENEMY_TORP_SPEED_KN)
        self.range_nm = (prof.range_nm if prof is not None
                         else config.ENEMY_TORP_RANGE_NM)

    @property
    def dead(self) -> bool:
        return self.state != "RUN"

    @property
    def speed_nm_per_s(self) -> float:
        return config.kn_to_nm_per_s(self.speed_kn)

    def update(self, dt: float, ship) -> None:
        if self.state != "RUN":
            return
        dist_before = math.hypot(ship.x - self.x, ship.y - self.y)
        if dist_before <= 3.0:
            desired = math.degrees(math.atan2(
                ship.x - self.x, -(ship.y - self.y))) % 360.0
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -6.0 * dt, 6.0 * dt)) % 360.0
        step = self.speed_nm_per_s * dt
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step

        if math.hypot(ship.x - self.x, ship.y - self.y) <= config.ENEMY_TORP_HIT_DIST_NM:
            self.state = "HIT"
        elif self.travel >= self.range_nm:
            self.state = "SASE"

    # --- Duck-Type-Interface wie Sub/Animal (passives Sonar) ---

    def distance_nm(self, ship) -> float:
        return math.hypot(self.x - ship.x, self.y - ship.y)

    def bearing_from_frigate(self, ship) -> float:
        dx = self.x - ship.x
        dy = self.y - ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    def quiet_factor(self) -> float:
        return config.ENEMY_TORP_QUIET

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Kreisch-Linie: 150->90 Hz ueber die Laufstrecke, plus
        Unterharmonische (45-75 Hz) im DEMON-Trennbereich."""
        if self.state != "RUN":
            return []
        frac = min(1.0, self.travel / max(0.001, self.range_nm))
        f = 150.0 - 60.0 * frac
        return [(f * 0.5, 0.35, 5.0), (f, 0.90, 8.0)]

    def broadband(self) -> dict:
        prof = CATALOG.get_torpedo("enemy_torp")
        if prof is not None and prof.acoustic is not None \
                and prof.acoustic.broadband is not None \
                and self.state == "RUN":
            lv, lo, hi = prof.acoustic.broadband
            return {"level": lv, "low_hz": lo, "high_hz": hi}
        return {}

    def acoustic_signature(self) -> str:
        if self.state != "RUN":
            return ""
        prof = CATALOG.get_torpedo("enemy_torp")
        text = prof.acoustic.signature_text if (prof and prof.acoustic) \
            else "hochfrequentes Kreischen"
        return f"mechanisch · {text} (Torpedo?)"

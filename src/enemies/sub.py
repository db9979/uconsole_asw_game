"""U-Boot-Modell: Typen-Daten aus dem Kontakt-Katalog + Patrouillen/Ausweich-KI (M2).

Pro Instanz: sensor_seed + Fingerprint (Blattzahl, Raten-Skala, Tonal-Offsets,
Kavitation/Breitband-Level) – Details in docs/contacts-db.md.
"""

import math
import random
from types import SimpleNamespace

from src.core import config
from src.data import catalog
from src.data import fingerprint as fingerprint_mod
from src.weapons.torpedo import underwater_path_blocked

CATALOG = catalog.CATALOG
DECOY_PROFILE = CATALOG.get_decoy("decoy")
if DECOY_PROFILE is None:
    raise RuntimeError(
        "Kontaktkatalog unvollstaendig: Dekoy-Profil 'decoy' fehlt")


class SubType:
    """Statik eines U-Boot-Typs (Captain's Log §2)."""

    def __init__(self, key, name, max_depth_m, torpedoes, quiet, speed_kn,
                 aggression, profile, acoustic):
        self.key = key
        self.name = name
        self.max_depth_m = max_depth_m
        self.torpedoes = torpedoes
        self.quiet = quiet          # 0 = laut ... 1 = stumm
        self.speed_min_kn, self.speed_kn = speed_kn
        self.aggression = aggression  # Angriffswahrscheinlichkeit (M5)
        self.profile = profile      # SubProfile (Kontakt-Katalog)
        self.acoustic = acoustic    # TargetSignature


SUB_TYPES = {
    p.key: SubType(p.key, p.name, p.max_depth_m, p.torpedoes, p.quiet,
                    p.speed_kn, p.aggression, p, p.acoustic)
    for p in CATALOG.subs.values()
}


class Sub:
    """U-Boot mit einfacher KI: PATROLLE <-> EVADE (M2)."""

    _next_id = 1

    def __init__(self, x_nm: float, y_nm: float, depth_m: float,
                 course_deg: float, stype_key: str, rng: random.Random,
                 quiet_mult: float = 1.0, attack_mult: float = 1.0,
                 attack_cooldown_s: float = None):
        self.id = Sub._next_id
        Sub._next_id += 1
        self.rng = rng
        self.stype = SUB_TYPES[stype_key]
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.fingerprint = fingerprint_mod.roll_from_seed(
            self.sensor_seed, self.stype.acoustic)
        self.quiet_mult = quiet_mult        # M7: Level-Faktor (leicht = lauter)
        self.attack_mult = attack_mult      # M7: Level-Faktor Gegenangriff
        self.attack_cooldown = (config.SUB_ATTACK_COOLDOWN_S
                                if attack_cooldown_s is None else attack_cooldown_s)
        self.x = x_nm
        self.y = y_nm
        self.start_pos = (x_nm, y_nm)   # M6: Flucht-Erkennung
        self.depth = depth_m
        self.course = course_deg % 360.0
        self.target_course = self.course
        self.target_depth = depth_m
        self.speed = rng.uniform(self.stype.speed_min_kn,
                                 min(self.stype.speed_kn, 8.0))
        self.state = "PATROLLE"
        self.evac_left = 0.0
        self.turn_left = rng.uniform(300.0, 900.0)
        self.turn_delta = 0.0
        self.evade_offset = rng.uniform(-30.0, 30.0)
        self._lofar_phase = 0.0  # M11: LOFAR-Pulsphase
        self.sunk = False
        self.heard_ping = False
        self.damage = 0.0     # 0..100
        self.sink_left = 0.0  # Sekunden bis versenkt (Zustand SINKING)
        # M5: Gegenschlag
        self.torpedoes_left = self.stype.torpedoes
        self.attack_left = self.attack_cooldown
        self.pending_torpedoes: list[tuple[float, float, float, float]] = []
        # (x, y, course_deg, depth_m) – wird vom Game zu EnemyTorpedo aufgesammelt
        # W2: Torpedo-Alarm + Dekoy
        self.torpedo_alerted = False   # eigener Torpedo gehört -> harte Reaktion
        self.pending_decoys: list[tuple[float, float]] = []
        self._decoy_cd = 0.0
        # Taktisches Gedaechtnis: nur Ereignisse, die das Boot wahrnimmt.
        self.memory = {
            "last_ping_age": float("inf"),
            "last_torpedo_age": float("inf"),
            "contact_bearing": None,
            "contact_age": config.SUB_EVADE_DURATION_S,
            "contact": None,
        }
        self.decision_reason = "Patrouille"

    # --- Ereignisse ---

    def hear_ping(self) -> None:
        """U-Boot hört einen aktiven Ping -> Ausweichen."""
        if not self.sunk and self.state != "SINKING":
            self.state = "EVADE"
            self.evac_left = config.SUB_EVADE_DURATION_S
            self.heard_ping = True
            self.memory["last_ping_age"] = 0.0
            self.evade_offset = self.rng.uniform(-30.0, 30.0)
            self.decision_reason = "Aktives Sonar gehoert: Ausweichen"

    def alert_torpedo(self) -> None:
        """W2: Feindtorpedo gehört -> harte Ausweichreaktion + ggf. Dekoy."""
        if not self.sunk and self.state != "SINKING":
            self.torpedo_alerted = True
            self.heard_ping = True
            self.state = "EVADE"
            self.evac_left = max(self.evac_left, config.SUB_EVADE_DURATION_S)
            self.memory["last_torpedo_age"] = 0.0
            self.evade_offset = self.rng.uniform(-35.0, 35.0)
            self.decision_reason = "Torpedoalarm: Ausweichen und Dekoy pruefen"

    def utility_scores(self, distance_nm: float, thermo_depth_m: float,
                       frigate_noise: float) -> dict[str, float]:
        """Bewertet taktische Optionen aus lokaler Information.

        Die KI bekommt keine Zielposition aus dem Spielzustand. Werte dienen
        zugleich als Debug-/Balancing-Schnittstelle.
        """
        under_thermo = self.depth >= thermo_depth_m
        threat = max(0.0, 1.0 - distance_nm / 40.0)
        return {
            "hide": (0.55 if under_thermo else 0.25) + threat * 0.30,
            "lurk": (0.45 if distance_nm < config.SUB_LUER_DIST_NM else 0.10)
                    + (0.20 if under_thermo else 0.0),
            "attack": (0.25 + frigate_noise * 0.45
                       + self.stype.aggression * 0.20
                       - distance_nm / 120.0),
            "escape": (self.damage / 100.0) * 0.75
                      + (0.25 if self.torpedoes_left == 0 else 0.0),
        }

    def tactical_decision(self, distance_nm: float, thermo_depth_m: float,
                          frigate_noise: float) -> str:
        """Liefert die beste lokale Utility-Aktion und merkt den Grund."""
        scores = self.utility_scores(distance_nm, thermo_depth_m, frigate_noise)
        action = max(scores, key=scores.get)
        self.decision_reason = f"{action}: {scores[action]:.2f}"
        return action

    def hit(self) -> None:
        """Torpedotreffer: Schaden; bei 100 % Sinkbeginn (Captain's Log §3)."""
        if self.sunk or self.state == "SINKING":
            return
        self.damage = min(100.0, self.damage + self.rng.uniform(60.0, 100.0))
        if self.damage >= 100.0:
            self.state = "SINKING"
            self.sink_left = 20.0
        else:
            self.state = "EVADE"
            self.evac_left = max(self.evac_left, config.SUB_EVADE_DURATION_S)

    # --- M5: Gegenschlag ---

    def _launch_data(self, frigate) -> tuple[float, float, float, float]:
        """Abzugsdaten: Interzeptions-Kurs mit Vorlauf + Kursfehler."""
        dist = self.distance_nm(frigate)
        enemy_speed = config.kn_to_nm_per_s(
            CATALOG.get_torpedo("enemy_torp").speed_kn)
        lead_s = dist / max(enemy_speed, 0.001)
        fr_speed = config.kn_to_nm_per_s(frigate.speed)
        px = frigate.x + fr_speed * lead_s * math.sin(math.radians(frigate.course))
        py = frigate.y - fr_speed * lead_s * math.cos(math.radians(frigate.course))
        course = math.degrees(math.atan2(px - self.x, -(py - self.y))) % 360.0
        course = (course + self.rng.uniform(-3.0, 3.0)) % 360.0
        return (self.x, self.y, course, self.rng.uniform(5.0, 12.0))

    def _maybe_attack(self, dt: float, frigate) -> None:
        """Gegenschlag, wenn die Fregatte laut/pinged wurde (Captain's Log §2.2)."""
        if self.sunk or self.state == "SINKING":
            return
        self.attack_left -= dt
        if self.attack_left > 0 or self.torpedoes_left <= 0:
            return
        if frigate is None:
            return
        dist = self.distance_nm(frigate)
        noise = frigate.noise_level()
        rate = 0.0
        if self.state == "EVADE" and self.heard_ping and dist < 20.0:
            rate = 0.006 * (0.5 + noise) * self.stype.aggression
        elif noise >= 0.75 and dist < 18.0:
            rate = 0.002 * self.stype.aggression
        rate *= self.attack_mult
        if rate > 0 and self.rng.random() < rate * dt:
            n = min(2 if dist < 12.0 and self.stype.aggression > .8 else 1,
                    self.torpedoes_left)
            for _ in range(n):
                self.pending_torpedoes.append(self._launch_data(frigate))
            self.torpedoes_left -= n
            self.attack_left = self.attack_cooldown

    # --- M13: Schnorcheln / Funk ---

    @property
    def transmitting(self) -> bool:
        """SNOCKEL mit aktivem HF-Sender -> peilbar per HFDF."""
        return self.state == "SNOCKEL"

    # --- Physik/KI ---

    def update(self, dt: float, frigate, world) -> None:
        """dt in Simulationssekunden; bei 1x identisch zu Echtzeit."""
        if self.sunk:
            return
        depth_at = getattr(world, "depth_m", lambda x, y: 1000.0)
        bottom = depth_at(self.x, self.y)
        safe_depth = min(self.stype.max_depth_m, max(0.0, bottom - 25.0))
        self.target_depth = config.clamp(self.target_depth, 0.0, safe_depth)
        old_depth = self.depth
        for key in ("last_ping_age", "last_torpedo_age"):
            if self.memory[key] != float("inf"):
                self.memory[key] += dt
        thermo = world.thermocline_depth_m(self.x, self.y)
        world_size = world.size_nm
        self._decoy_cd = max(0.0, self._decoy_cd - dt)

        # W2: Torpedo-Alarm -> einmalig Dekoy-Abwurf (Chance je Level-Faktor)
        if self.torpedo_alerted and self._decoy_cd <= 0.0:
            if self.rng.random() < DECOY_PROFILE.chance:
                self.pending_decoys.append((self.x, self.y))
                self._decoy_cd = DECOY_PROFILE.cooldown_s
            self.torpedo_alerted = False

        if self.state == "SINKING":
            self.sink_left = max(0.0, self.sink_left - dt)
            self.depth += 3.0 * dt
            self.speed = 0.0
            if self.sink_left <= 0:
                self.state = "SUNK"
                self.sunk = True
            return

        # Retain only a bounded local acoustic observation, never a live ship
        # reference. Ping memory does not continuously refresh hidden motion.
        self.memory["contact_age"] = min(config.SUB_EVADE_DURATION_S,
                                         self.memory["contact_age"] + dt)
        distance = self.distance_nm(frigate)
        noise = frigate.noise_level()
        received_ping = self.memory["last_ping_age"] <= dt
        if (distance < 20.0 and (received_ping or (noise >= 0.75 and distance < 18.0))
                and not getattr(world, "sonar_path_blocked", lambda *args: False)(
                    self.x, self.y, self.depth, frigate.x, frigate.y, 5.0)):
            self.memory["contact"] = dict(x=frigate.x, y=frigate.y,
                                           speed=frigate.speed, course=frigate.course,
                                           noise=noise)
            self.memory["contact_age"] = 0.0
            self.memory["contact_bearing"] = math.degrees(math.atan2(
                frigate.x - self.x, -(frigate.y - self.y))) % 360.0
        if self.memory["contact_age"] >= config.SUB_EVADE_DURATION_S:
            self.memory["contact"] = None
            self.memory["contact_bearing"] = None
        observed = self.memory["contact"]
        contact = (SimpleNamespace(**observed, noise_level=lambda: observed["noise"])
                   if observed is not None else None)
        self._maybe_attack(dt, contact)

        if self.state == "SNOCKEL":
            # M13: Schnorcheltiefe ~8 m, HF-Sender aktiv, kein Vordringen
            self.evac_left -= dt
            self.target_depth = min(8.0, safe_depth)
            self.depth += config.clamp(self.target_depth - self.depth, -.8 * dt, .8 * dt)
            self.speed = 0.0
            if self.evac_left <= 0:
                self.state = "PATROLLE"
                self.speed = min(6.0, self.speed_for_state())
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.turn_delta = 0.0
            return

        if self.state == "EVADE":
            self.evac_left -= dt
            if self.evac_left <= 0:
                # W2: In der Nähe der Fregatte -> still halten und lauschen
                if contact is not None and self.distance_nm(contact) < config.SUB_LUER_DIST_NM:
                    self.state = "LAUER"
                    self.evac_left = self.rng.uniform(*config.SUB_LUER_DURATION_S)
                    self.heard_ping = False
                    self.speed = 0.5
                else:
                    self.state = "PATROLLE"
                    self.heard_ping = False
                    self.speed = min(6.0, self.speed_for_state())
                    self.target_depth = min(safe_depth, self.rng.uniform(40.0, 80.0))
                    self.turn_left = self.rng.uniform(300.0, 900.0)
                    self.turn_delta = 0.0
                return
            # Tiefer unter die Thermokline + Kurs ab der Fregatte
            self.target_depth = min(thermo + 40.0, safe_depth)
            self.depth += config.clamp(self.target_depth - self.depth, -1.5 * dt, 1.5 * dt)
            bearing = self.memory["contact_bearing"]
            target_course = (self.course if bearing is None else
                             (bearing + 180.0 + self.evade_offset) % 360.0)
            diff = config.angle_diff_deg(target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -1.5 * dt, 1.5 * dt)) % 360.0
            self.speed = max(self.speed, min(self.speed_for_state(),
                                             max(10.0, self.stype.speed_kn * .9)))
        elif self.state == "LAUER":
            # W2: Stillhalten unter der Thermokline (sehr leise, lauschen)
            self.evac_left -= dt
            self.target_depth = min(thermo + 15.0, safe_depth)
            self.depth += config.clamp(self.target_depth - self.depth, -.5 * dt, .5 * dt)
            self.speed = max(1.0, self.speed - .08 * dt)
            if self.evac_left <= 0:
                self.state = "PATROLLE"
                self.speed = min(6.0, self.speed_for_state())
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.turn_delta = 0.0
        else:
            # Patrouille: lange, ruhige Legs statt dauernder Kreisfahrt.
            self.turn_left -= dt
            if self.turn_left <= 0:
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.target_course = (self.course
                                      + self.rng.uniform(-45.0, 45.0)) % 360.0
                self.target_depth = self.rng.uniform(
                    40.0, min(self.stype.max_depth_m, max(80.0, thermo + 30.0)))
                patrol_max = min(8.0, self.speed_for_state())
                self.speed = self.rng.uniform(
                    min(3.0, patrol_max), max(min(3.0, patrol_max), patrol_max))
            diff = config.angle_diff_deg(self.target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -.6 * dt, .6 * dt)) % 360.0
            self.target_depth = config.clamp(self.target_depth, 0.0, safe_depth)
            self.depth += config.clamp(
                self.target_depth - self.depth, -.5 * dt, .5 * dt)
            # M13: Diesel/AIP: im Tiefebereich gelegentlich Schnorcheln (HF-Senden)
            if (self.stype.profile.requires_air and self.depth > 55.0
                    and self.rng.random() < config.SNOCKEL_TRIGGER_PPS * dt):
                self.state = "SNOCKEL"
                self.evac_left = config.SNOCKEL_DURATION_S

        v = config.kn_to_nm_per_s(self.speed) * dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        if (world.on_land(nx, ny) or underwater_path_blocked(
                world, self.x, self.y, old_depth + 25.0 - 1e-6,
                nx, ny, self.depth + 25.0 - 1e-6)):
            self.target_course = (self.course + 90.0) % 360.0
            self.course = self.target_course
        else:
            self.x, self.y = nx, ny

        # Welt-Rand: Kurs spiegeln (nautisch: x-Rand -> 360-C, y-Rand -> 180-C)
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)

    # --- Akustik ---

    def quiet_factor(self) -> float:
        """Stillheit: Sprint/Ausweichen laut, LAUER besonders leise."""
        q = self.stype.quiet * self.quiet_mult - 0.30 * (self.damage / 100.0)
        if self.state == "EVADE":
            q -= 0.30
        if self.state == "LAUER":
            q = max(0.97, q + 0.08)
        if self.transmitting:
            q += config.SNOCKEL_TRANSMIT_NOISE  # M13: Senden macht lauter
        return config.clamp(q, 0.0, 1.0)

    def acoustic_signature(self) -> str:
        """M9: Hörbare Geräusch-Signatur für manuelle Klassifizierung.

        Kein exakter Typ, sondern das, was ein Hörposten wahrnehmen würde:
        Antriebsart + aktuelle Frequenz (Fahrt/Zustand).
        """
        if self.sunk:
            return ""
        if self.transmitting:
            return "mechanisch · Funkverkehr (HF), Sender aktiv"
        base = self.stype.acoustic.signature_text or "unbekanter Antrieb"
        if self.state == "EVADE":
            freq = "Frequenz hoch (Ausweichmanöver)"
        elif self.speed >= 10.0:
            freq = "Frequenz hoch (schnelle Fahrt)"
        else:
            freq = "Frequenz niedrig (Langfahrt)"
        detail = (f" · DEMON {self.stype.acoustic.tonal_band_hz[0]:.0f}-"
                  f"{self.stype.acoustic.tonal_band_hz[1]:.0f} Hz")
        return f"mechanisch · {base} · {freq}{detail}"

    def speed_for_state(self) -> float:
        """Fahrt bei Schaden: langsamer je nach Schadensgrad."""
        return self.stype.speed_kn * (1.0 - 0.25 * self.damage / 100.0)

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        """Nautische Peilung: 0° = Nord (nach oben), 90° = Ost, im Uhrzeigersinn."""
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    # --- M11/W1: LOFAR-Signatur + Breitband ---

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Diskrete Frequenzlinien (freq_hz, amp 0..1, Breite in Bins).

        Hauptschraube-Linie (Frequenz folgt der Fahrt über das Profil-Band,
        pro Instanz per Fingerprint versetzt), Harmonische bei schneller
        Fahrt, Getriebe-Tonals aus dem Profil, HF-Sender beim Schnorcheln
        und Schadens-Grundrauschen bei hoher Schädigung."""
        if self.sunk:
            return []
        lines = []
        v = max(0.0, self.speed)
        sig = self.stype.acoustic
        fp = self.fingerprint
        vmax = max(1.0, self.stype.speed_kn)
        if v > 0.5:
            f = (fp.rate_scale
                 * (sig.tonal_band_hz[0]
                    + (sig.tonal_band_hz[1] - sig.tonal_band_hz[0])
                    * min(1.0, v / vmax))
                 + fp.offsets[0])
            f = max(2.0, f)
            amp = 0.25 + 0.55 * min(1.0, v / 18.0)
            if self.state == "EVADE":
                f *= 1.2
                amp = min(1.0, amp + 0.30)
            if self.state == "LAUER":
                amp *= 0.5
            lines.append((f, amp, 1.5))
            if v > 4.0:
                lines.append((f * 2.0 + fp.offsets[1], amp * 0.5, 1.2))
                lines.append((f * 3.0 + fp.offsets[2], amp * 0.3, 1.0))
            for hz, a, width in sig.secondary_tonals:
                lines.append((hz, a * min(1.0, v / 6.0), width))
        if self.transmitting:
            lines.append((20.0, 0.95, 2.0))
            lines.append((35.0, 0.70, 1.5))
        if self.damage > 30.0:
            lines.append((55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0))
        return lines

    def broadband(self) -> dict:
        """Breitbandige Rausch-Quelle (level 0..1 + Band) für Audio/BTR."""
        sig = self.stype.acoustic
        if self.sunk or sig.broadband is None:
            return {}
        v = max(0.0, self.speed)
        vmax = max(1.0, self.stype.speed_kn)
        level = self.fingerprint.bb_level * (0.15 + 0.85 * min(1.0, v / vmax))
        if self.state == "EVADE":
            level *= 1.6
        if self.state == "LAUER":
            level *= 0.5
        level = min(1.0, level + 0.10 * (self.damage / 100.0))
        return {"level": min(1.0, level),
                "low_hz": sig.broadband[1],
                "high_hz": sig.broadband[2]}

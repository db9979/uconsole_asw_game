"""Missions-System (M6): seed-basierte Typ-Auswahl + Spawn-Plan + Zieltext."""

import random

from src.core import config


class Mission:
    """Eine Mission: Typ, Zeitlimit, Spawn-Plan (deterministisch aus Seed).

    W4: type_key gesetzt -> fixer Typ (aus Szenario), MISSION_TYPES-Ranges.
    type_key=None -> frei komponiert direkt aus den Custom-Difficulty-Werten
    des Spielers (``difficulty``, siehe ``config.DIFFICULTY_FIELDS``).
    """

    def __init__(self, seed: int, type_key: str = None, difficulty: dict = None):
        self.seed = seed
        rng = random.Random(seed * 7919 + 13)
        difficulty = difficulty or config.DEFAULT_DIFFICULTY

        if type_key and type_key in config.MISSION_TYPES:
            self.type_key = type_key
            self.spec = config.MISSION_TYPES[self.type_key]
            self.name = self.spec["name"]
            self.win_mode = self.spec["win"]            # "sink" | "survive"
            self.time_limit_s = self.spec["time_limit_s"]  # reelle Sekunden
            self.sub_count = self.spec["subs"]
            self.sub_types = [rng.choice(self.spec["sub_types"])
                              for _ in range(self.sub_count)]
            self.animal_count = rng.randint(*self.spec["animals"])
            self.civilian_count = rng.randint(*self.spec["civilians"])
            self.asm_count = rng.randint(*self.spec["asm"])  # M16
            self.warship_count = rng.randint(*self.spec.get("warships", (0, 0)))
        else:
            # Freie Jagd (s4_zufall): komplett aus der Spielerwahl komponiert,
            # kein gewichteter Zufalls-Typ mehr.
            self.type_key = "custom"
            self.spec = None
            self.name = "Freie Jagd"
            self.sub_count = int(difficulty["sub_count"])
            sub_pool = ["diesel_alt", "aip_modern", "ssn"]
            self.sub_types = [rng.choice(sub_pool) for _ in range(self.sub_count)]
            self.win_mode = "sink" if self.sub_count > 0 else "survive"
            self.time_limit_s = float(difficulty["time_limit_s"])
            self.animal_count = int(difficulty["animal_count"])
            self.civilian_count = int(difficulty["civilian_count"])
            self.asm_count = int(difficulty["air_raid_count"])
            self.warship_count = int(difficulty["warship_count"])

        # Luftangriffs-Taktung: einmalig aus der gewählten Häufigkeit
        # abgeleitet und gecacht - nie wieder aus config neu berechnet
        # (gleiches Muster wie Sub.quiet_mult etc.).
        freq_mult = float(difficulty["air_raid_freq_mult"])
        self.asm_interval_s = config.ASM_SPAWN_INTERVAL_S / freq_mult
        self.raid_interval_s = config.RAID_WAVE_INTERVAL_S / freq_mult

    @property
    def objective(self) -> str:
        """Kurze Zielbeschreibung für die Anzeige."""
        if self.win_mode == "survive":
            base = "Konvoi: Zeitlimit durchhalten"
        elif self.type_key == "nuklearer_abfang":
            base = "SSN vor Zeitablauf versenken"
        else:
            base = "Alle U-Boote versenken"
        if self.asm_count:
            base += f" | {self.asm_count}× ASM! | Luftangriffe!"
        if self.warship_count:
            base += f" | {self.warship_count}× feindliches Oberflächenschiff!"
        return base

    def remaining_s(self, elapsed_s: float) -> float:
        return max(0.0, self.time_limit_s - elapsed_s)

    def format_remaining(self, elapsed_s: float) -> str:
        s = int(self.remaining_s(elapsed_s))
        return f"{s // 60:02d}:{s % 60:02d}"

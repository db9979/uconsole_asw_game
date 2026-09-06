"""Missions-System (M6): seed-basierte Typ-Auswahl + Spawn-Plan + Zieltext."""

import random

from src.core import config


class Mission:
    """Eine Mission: Typ, Zeitlimit, Spawn-Plan (deterministisch aus Seed).

    W4: type_key=None -> seed-basierte Gewichtsziehung; sonst fixer Typ
    (aus Szenario).
    """

    def __init__(self, seed: int, type_key: str = None):
        self.seed = seed
        rng = random.Random(seed * 7919 + 13)

        if type_key and type_key in config.MISSION_TYPES:
            self.type_key = type_key
        else:
            total_weight = sum(t["weight"] for t in config.MISSION_TYPES.values())
            roll = rng.randint(0, total_weight - 1)
            acc = 0
            self.type_key = "patrouille"
            for key, spec in config.MISSION_TYPES.items():
                acc += spec["weight"]
                if roll < acc:
                    self.type_key = key
                    break
        self.spec = config.MISSION_TYPES[self.type_key]

        self.name = self.spec["name"]
        self.win_mode = self.spec["win"]            # "sink" | "survive"
        self.time_limit_s = self.spec["time_limit_s"]  # reelle Sekunden
        self.sub_count = self.spec["subs"]
        self.sub_types = [rng.choice(self.spec["sub_types"])
                          for _ in range(self.sub_count)]
        self.animal_count = rng.randint(*self.spec["animals"])
        self.civilian_count = rng.randint(*self.spec["civilians"])
        self.asm_count = rng.randint(*self.spec["asm"])  # M16 (nach M6-Rolls: Determinismus)
        self.warship_count = rng.randint(*self.spec.get("warships", (0, 0)))

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
            base += f" | {self.asm_count}× ASM!"
        if self.warship_count:
            base += f" | {self.warship_count}× feindliches Oberflächenschiff!"
        return base

    def remaining_s(self, elapsed_s: float) -> float:
        return max(0.0, self.time_limit_s - elapsed_s)

    def format_remaining(self, elapsed_s: float) -> str:
        s = int(self.remaining_s(elapsed_s))
        return f"{s // 60:02d}:{s % 60:02d}"

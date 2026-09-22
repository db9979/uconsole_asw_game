"""Stationen an Bord der Fregatte."""

from enum import Enum


class Station(Enum):
    BRIDGE = "Brücke"
    SONAR = "Sonarzentrale"
    WEAPONS = "Waffenzentrale"
    DAMAGE = "Schadensbekämpfung"
    OPZ = "OPZ/CIC"
    RADAR = "OPZ/CIC"  # Kompatibilitaetsalias, keine eigene Station
    RADIO = "Funk"
    ENGINE = "Maschinenraum"
    HELICOPTER = "Helikopter-Deck"
    ELOKA = "EloKa"

    @property
    def label(self) -> str:
        return self.value

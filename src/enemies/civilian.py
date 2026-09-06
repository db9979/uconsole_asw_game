"""Zivile Schiffe – Kompatibilitaets-Import.

CivilianShip ist jetzt ein Alias fuer SurfaceShip (zivile Variante).
Neues Spiel: src/enemies/surface.py.
"""

from src.enemies.surface import SurfaceShip as CivilianShip

__all__ = ["CivilianShip"]

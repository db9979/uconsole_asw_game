"""Render deterministic README screenshots with SDL's headless drivers."""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from src.core import config
from src.core.game import Game
from src.core.preferences import Preferences
from src.core.station import Station


STATIONS = (
    (Station.BRIDGE, "bridge"),
    (Station.SONAR, "sonar"),
    (Station.WEAPONS, "weapons"),
    (Station.DAMAGE, "damage-control"),
    (Station.OPZ, "opz-cic"),
    (Station.RADIO, "radio"),
    (Station.ENGINE, "engineering"),
    (Station.HELICOPTER, "helicopter"),
    (Station.ELOKA, "eloka"),
)


def _preferences() -> Preferences:
    return Preferences(language="en", fullscreen=False, audio=False,
                       large_text=False, tooltips=True)


def _capture(game: Game) -> pygame.Surface:
    game.draw()
    return game.screen.copy()


def _save(surface: pygame.Surface, path: Path) -> None:
    pygame.image.save(surface, path)


def _montage(images: list[pygame.Surface]) -> pygame.Surface:
    width, height = config.SCREEN_W, config.SCREEN_H
    columns = 1 if len(images) == 1 else 2
    rows = max(1, (len(images) + columns - 1) // columns)
    result = pygame.Surface((width * columns, height * rows))
    for index, image in enumerate(images):
        result.blit(image, ((index % columns) * width,
                            (index // columns) * height))
    return result


def capture_all(output_dir: Path, seed: int = 1234) -> list[Path]:
    """Capture the main menu and every workstation; return written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    menu = Game(seed=seed, start_menu=True, show_splash=False,
                fullscreen=False, audio_enabled=False,
                preferences=_preferences())
    menu_surface = _capture(menu)
    menu_path = output_dir / "main-menu.png"
    _save(menu_surface, menu_path)
    written.append(menu_path)
    menu.audio.shutdown()

    game = Game(seed=seed, start_menu=False, show_splash=False,
                fullscreen=False, audio_enabled=False,
                preferences=_preferences())
    # Build a representative observation history through normal simulation.
    for _ in range(360):
        game.update(1.0 / config.FPS)
    game.msg_until = 0.0
    game.sonar_page = 1  # LOFAR is the most representative passive display.

    station_images: list[pygame.Surface] = []
    for station, filename in STATIONS:
        game.station = station
        image = _capture(game)
        path = output_dir / f"station-{filename}.png"
        _save(image, path)
        written.append(path)
        station_images.append(image)

    groups = (station_images[:4], station_images[4:8], station_images[8:])
    for index, group in enumerate(groups, 1):
        path = output_dir / f"stations-overview-{index}.png"
        _save(_montage(group), path)
        written.append(path)

    # Authored own-ship damage demonstration, separate from the live screenshots.
    game.damage = copy.deepcopy(game.damage)
    for key, state, flood, fire in (
            ("sonar", "FLUTEND", 48., 0.),
            ("engine", "BESCHAEDIGT", 18., 37.),
            ("flightdeck", "ZERSTOERT", 70., 0.)):
        compartment = game.damage.compartments[key]
        compartment.state, compartment.flood, compartment.fire = state, flood, fire
    game.damage.total = sum(c.flood for c in game.damage.compartments.values())
    game.damage.teams = {1: "sonar", 2: "engine", 3: "engine"}
    game.dmg_cursor = list(game.damage.compartments).index("engine")
    game.dmg_team = 2
    game.station = Station.DAMAGE
    path = output_dir / "damage-control-alert.png"
    _save(_capture(game), path)
    written.append(path)

    # Listener remains off; no live pairing code is recorded in documentation.
    game._open_administration("commander")
    path = output_dir / "commander-options.png"
    _save(_capture(game), path)
    written.append(path)

    game.audio.shutdown()
    pygame.quit()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "screenshots")
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args(argv)
    for path in capture_all(args.output, args.seed):
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

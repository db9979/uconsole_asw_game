"""Render deterministic README screenshots with SDL's headless drivers."""

from __future__ import annotations

import argparse
import copy
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.preferences import Preferences
from src.core.station import Station
from src.data.catalog import CATALOG
from src.data.user_content import UserContentStore
from src.ui.mission_editor import MissionEditor
from src.ui.unit_editor import UnitEditor, catalog_builtins


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

LANGUAGES = ("en", "de")
SONAR_PAGES = (
    "broadband",
    "lofar",
    "demon",
    "tma",
    "environment-fusion",
    "active",
)


def _preferences(language: str) -> Preferences:
    return Preferences(language=language, fullscreen=False, audio=False,
                        large_text=False, tooltips=True)


def _capture(game: Game) -> pygame.Surface:
    game.draw()
    return game.screen.copy()


def _save(surface: pygame.Surface, path: Path) -> None:
    pygame.image.save(surface, path)


def _capture_to(game: Game, output_dir: Path, language: str, filename: str,
                written: list[Path]) -> pygame.Surface:
    image = _capture(game)
    path = output_dir / (filename if language == "en" else f"{language}-{filename}")
    _save(image, path)
    written.append(path)
    return image


def _set_capture_language(game: Game, language: str) -> None:
    """Switch display language without persisting a screenshot preference."""
    game.preferences = replace(game.preferences, language=language)
    game.translator = Translator(language)
    game.tr = game.translator.t
    pygame.display.set_caption(game.tr("app.title"))
    if game.editor is not None:
        game.editor.tr = game.tr


def _montage(images: list[pygame.Surface]) -> pygame.Surface:
    width, height = config.SCREEN_W, config.SCREEN_H
    columns = 1 if len(images) == 1 else 2
    rows = max(1, (len(images) + columns - 1) // columns)
    result = pygame.Surface((width * columns, height * rows))
    for index, image in enumerate(images):
        result.blit(image, ((index % columns) * width,
                            (index // columns) * height))
    return result


def capture_all(output_dir: Path, seed: int = 1234,
                languages: tuple[str, ...] = LANGUAGES) -> list[Path]:
    """Capture localized native views without accessing real user storage."""
    requested = set(languages)
    if not requested or not requested <= set(LANGUAGES):
        raise ValueError(f"languages must contain only {LANGUAGES!r}")
    selected_languages = tuple(language for language in LANGUAGES
                               if language in requested)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    original_home = os.environ.get("HOME")
    original_save_dir = config.SAVE_DIR
    original_save_path = config.SAVE_PATH
    with tempfile.TemporaryDirectory(prefix="u-jagd-screenshots-") as home:
        os.environ["HOME"] = home
        content_root = Path(home) / ".u-jagd"
        config.SAVE_DIR = str(content_root)
        config.SAVE_PATH = str(content_root / "save.json")
        store = UserContentStore(content_root)
        menu: Game | None = None
        game: Game | None = None
        try:
            initial_language = selected_languages[0]
            menu = Game(seed=seed, start_menu=True, show_splash=False,
                        fullscreen=False, audio_enabled=False,
                        preferences=_preferences(initial_language))
            game = Game(seed=seed, start_menu=False, show_splash=False,
                        fullscreen=False, audio_enabled=False,
                        preferences=_preferences(initial_language))

            # Build one representative observation history for both languages.
            for _ in range(360):
                game.update(1.0 / config.FPS)
            game.msg_until = 0.0
            baseline_damage = copy.deepcopy(game.damage)
            baseline_dmg_cursor = game.dmg_cursor
            baseline_dmg_team = game.dmg_team
            builtins = catalog_builtins(CATALOG)

            for language in selected_languages:
                _set_capture_language(menu, language)
                _set_capture_language(game, language)

                menu.editor = None
                menu._open_administration("")
                menu.in_menu = True
                menu.main_menu = True
                menu.main_menu_sel = 0
                menu.msg = ""
                _capture_to(menu, output_dir, language, "main-menu.png", written)

                menu.main_menu = False
                menu.menu_screen = "scenario"
                menu.menu_sel = 0
                _capture_to(menu, output_dir, language,
                            "mission-scenario-selection.png", written)

                menu.scenario_key = config.SCENARIO_ORDER[0]
                menu.menu_screen = "briefing"
                _capture_to(menu, output_dir, language,
                            "mission-briefing.png", written)

                menu.main_menu = True
                menu._open_administration("options")
                _capture_to(menu, output_dir, language, "options.png", written)
                menu._open_administration("")

                profiles = set(builtins)
                menu.editor = MissionEditor(store=store, tr=menu.tr,
                                            profile_keys=profiles)
                _capture_to(menu, output_dir, language,
                            "mission-editor.png", written)

                menu.editor = UnitEditor(builtins, store=store, tr=menu.tr)
                _capture_to(menu, output_dir, language, "unit-editor.png", written)

                menu.editor = menu._make_analyzer()
                _capture_to(menu, output_dir, language,
                            "contact-analyzer.png", written)
                menu.editor = None

                game._open_administration("")
                game.damage = copy.deepcopy(baseline_damage)
                game.dmg_cursor = baseline_dmg_cursor
                game.dmg_team = baseline_dmg_team
                game.msg = ""
                game.sonar_page = 1  # Preserve the representative LOFAR station image.

                station_images: list[pygame.Surface] = []
                for station, filename in STATIONS:
                    game.station = station
                    station_images.append(_capture_to(
                        game, output_dir, language, f"station-{filename}.png", written))

                groups = (station_images[:4], station_images[4:8], station_images[8:])
                for index, group in enumerate(groups, 1):
                    filename = f"stations-overview-{index}.png"
                    path = output_dir / (filename if language == "en"
                                         else f"{language}-{filename}")
                    _save(_montage(group), path)
                    written.append(path)

                game.station = Station.SONAR
                for page, page_name in enumerate(SONAR_PAGES):
                    game.sonar_page = page
                    _capture_to(game, output_dir, language,
                                f"sonar-{page_name}.png", written)

                # Authored own-ship damage demonstration, separate from live views.
                for key, state, flood, fire in (
                        ("sonar", "FLUTEND", 48., 0.),
                        ("engine", "BESCHAEDIGT", 18., 37.),
                        ("flightdeck", "ZERSTOERT", 70., 0.)):
                    compartment = game.damage.compartments[key]
                    compartment.state = state
                    compartment.flood = flood
                    compartment.fire = fire
                game.damage.total = sum(
                    compartment.flood
                    for compartment in game.damage.compartments.values())
                game.damage.teams = {1: "sonar", 2: "engine", 3: "engine"}
                game.dmg_cursor = list(game.damage.compartments).index("engine")
                game.dmg_team = 2
                game.station = Station.DAMAGE
                _capture_to(game, output_dir, language,
                            "damage-control-alert.png", written)

                # Listener remains off; no live pairing code is recorded.
                game._open_administration("commander")
                _capture_to(game, output_dir, language,
                            "commander-options.png", written)
        finally:
            for owner in (menu, game):
                if owner is not None:
                    owner.commander.stop()
                    owner.audio.shutdown()
            config.SAVE_DIR = original_save_dir
            config.SAVE_PATH = original_save_path
            if original_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = original_home
            pygame.quit()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "screenshots")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--language", choices=("all", *LANGUAGES), default="all",
                        help="capture both languages or only one (default: all)")
    args = parser.parse_args(argv)
    languages = LANGUAGES if args.language == "all" else (args.language,)
    for path in capture_all(args.output, args.seed, languages):
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

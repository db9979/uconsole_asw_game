"""Mission debrief page: truth beside the crew's knowledge, after the end.

The page draws one recorded frame (``src/core/debrief.py``) at the cursor:
the ship's and every boat's true track so far, the crew's contacts where it
had placed them (bearing-only contacts as short bearing lines), weapons,
buoys and aircraft; beside it the headline numbers and the event list, and
below a timeline with a tick per event.  It is opened only from the end
panel, never while a mission runs.
"""

from __future__ import annotations

import math

import pygame

from src.core import config, debrief_replay
from src.core.i18n import localize, localized, message
from src.ui import llm_text, layout

PANEL = pygame.Rect(12, 12, 1256, 696)
MAP = pygame.Rect(24, 64, 780, 556)
SIDE = pygame.Rect(820, 64, 436, 556)
TIMELINE = pygame.Rect(24, 632, 1232, 30)
# Replay buttons in the title row: play/pause (Space) and 10x/60x (Tab).
PLAY = pygame.Rect(1040, 14, 104, 30)
SPEED = pygame.Rect(1152, 14, 104, 30)
EVENT_COLORS = {
    "first_contact": config.COLOR_WARN, "first_fix": config.COLOR_WARN,
    "classified": config.COLOR_WARN, "own_shot": config.COLOR_FLIGHT,
    "enemy_shot": config.COLOR_DANGER, "sub_sunk": config.COLOR_OK,
    "own_damage": config.COLOR_DANGER, "ship_sunk": config.COLOR_DANGER,
    "missed": config.COLOR_CONTACT_MISSILE, "pinged": config.COLOR_WARN,
    "mission_end": config.COLOR_TEXT,
}
OWN_COLOR = (90, 160, 255)


def _clock(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def event_text(event, prefix: str = "debrief.") -> str:
    """One event line; ``prefix`` is the recorder's perspective (frigate or boat)."""
    params = dict(event["params"])
    if event["kind"] == "missed":
        params["layer"] = localize(prefix + ("missed_layer" if params.get("layer")
                                             else "missed_open"))
    if event["kind"] == "pinged":
        params["source"] = localize("uboot.threat_page.kind." + str(params.get("source")))
    if event["kind"] == "mission_end":
        result = params.get("result")
        params["result"] = localize(
            "uboot.end." + result if prefix != "debrief." and result in (
                "won", "broke_through", "reported", "convoy_sunk", "passed", "landed",
                "supply_sunk", "escaped", "home", "picked_up", "elint", "shaken",
                "survived", "objective", "trained", "lost", "over")
            else "end.victory" if result == "SIEG" else "end.defeat")
    return localize(message(prefix + "event." + event["kind"],
                   **{key: str(value) for key, value in params.items()}))


def _bounds(recorder):
    """World box of everything recorded (cached until a frame is added)."""
    cache = getattr(recorder, "_view_bounds", None)
    if cache is not None and cache[0] == len(recorder.frames):
        return cache[1]
    xs, ys = [], []
    for frame in recorder.frames:
        xs.append(frame["ship"]["x"])
        ys.append(frame["ship"]["y"])
        for sub in frame["subs"]:
            if sub["hostile"]:
                xs.append(sub["x"])
                ys.append(sub["y"])
        for row in frame["known"]:
            if row["x"] is not None:
                xs.append(row["x"])
                ys.append(row["y"])
    if not xs:
        box = (0.0, 0.0, 10.0, 10.0)
    else:
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        span = max(4.0, max(xs) - min(xs), max(ys) - min(ys)) * 1.1
        box = (cx - span / 2.0, cy - span / 2.0, cx + span / 2.0, cy + span / 2.0)
    recorder._view_bounds = (len(recorder.frames), box)
    return box


def _projector(recorder):
    x0, y0, x1, y1 = _bounds(recorder)
    scale = min(MAP.w / (x1 - x0), MAP.h / (y1 - y0))
    ox = MAP.centerx - (x0 + x1) / 2.0 * scale
    oy = MAP.centery - (y0 + y1) / 2.0 * scale
    return (lambda x, y: (ox + x * scale, oy + y * scale)), scale


def timeline_index_at(game, pos) -> int | None:
    """Frame under a click on the timeline, or ``None``."""
    recorder = game.debrief
    if pos is None or not recorder.frames or not TIMELINE.collidepoint(pos):
        return None
    end = max(1e-6, recorder.frames[-1]["t"])
    return recorder.frame_index_at((pos[0] - TIMELINE.x) / TIMELINE.w * end)


@localized
def draw_debrief(game) -> None:
    s = game.screen
    recorder = game.debrief
    pygame.draw.rect(s, config.COLOR_OVERLAY_BG, PANEL)
    pygame.draw.rect(s, config.COLOR_TEXT_DIM, PANEL, 2)
    if not recorder.frames:
        layout.blit_line(s, "debrief.empty", PANEL.inflate(-40, -40), config.COLOR_TEXT_DIM,
                         size=22, align="center")
        return
    replay = game.debrief_replay
    game.advance_debrief_replay(game._t)
    index = max(0, min(game.debrief_index, len(recorder.frames) - 1))
    frame = debrief_replay.interpolate(recorder.frames, replay.t) or recorder.frames[index]
    layout.blit_line(s, message("debrief.title", time=_clock(frame["t"]),
                                end=_clock(recorder.frames[-1]["t"])),
                     (24, 18, 1000, 26), config.COLOR_TEXT, size=22)
    _draw_buttons(s, replay)
    _draw_map(game, s, recorder, index, frame)
    _draw_side(game, s, recorder, frame)
    _draw_timeline(s, recorder, frame)
    layout.blit_line(s, "debrief.keys", (24, 670, 1232, 26), config.COLOR_TEXT_DIM, size=16)


def replay_button_at(pos):
    """``"play"``/``"speed"`` under a click on the replay buttons, else None."""
    if pos is None:
        return None
    if PLAY.collidepoint(pos):
        return "play"
    if SPEED.collidepoint(pos):
        return "speed"
    return None


def _draw_buttons(s, replay) -> None:
    for rect, text, lit in ((PLAY, "debrief.pause" if replay.playing else "debrief.play",
                             replay.playing),
                            (SPEED, message("debrief.speed", speed=replay.speed), False)):
        pygame.draw.rect(s, config.COLOR_TAB_ACTIVE if lit else config.COLOR_PANEL_BG, rect)
        pygame.draw.rect(s, config.COLOR_SONAR_RING if lit else config.COLOR_GRID, rect, 1)
        layout.blit_line(s, text, rect.inflate(-8, -4), config.COLOR_TEXT, size=16,
                         align="center")


def _draw_map(game, s, recorder, index, frame) -> None:
    pygame.draw.rect(s, config.COLOR_GEO_BG, MAP)
    pygame.draw.rect(s, config.COLOR_GRID, MAP, 1)
    to_screen, scale = _projector(recorder)
    # The tracks grow up to the replay cursor (the interpolated frame).
    frames = [f for f in recorder.frames[:index + 1] if f["t"] < frame["t"]] + [frame]
    with layout.clip_to(s, MAP):
        # Grid every 5 NM (or coarser) as a scale.
        step = 5.0
        while step * scale < 40:
            step *= 2.0
        x0, y0, x1, y1 = _bounds(recorder)
        gx = math.floor(x0 / step) * step
        while gx <= x1:
            pygame.draw.line(s, config.COLOR_GEO_GRID, to_screen(gx, y0), to_screen(gx, y1), 1)
            gx += step
        gy = math.floor(y0 / step) * step
        while gy <= y1:
            pygame.draw.line(s, config.COLOR_GEO_GRID, to_screen(x0, gy), to_screen(x1, gy), 1)
            gy += step
        ship_path = [to_screen(f["ship"]["x"], f["ship"]["y"]) for f in frames]
        if len(ship_path) > 1:
            pygame.draw.lines(s, OWN_COLOR, False, ship_path, 2)
        paths = {}
        for f in frames:
            for sub in f["subs"]:
                if sub["hostile"]:
                    paths.setdefault(sub["id"], []).append(to_screen(sub["x"], sub["y"]))
        for points in paths.values():
            if len(points) > 1:
                pygame.draw.lines(s, config.COLOR_CONTACT_UBOOT, False, points, 1)
        for buoy in frame["buoys"]:
            pygame.draw.circle(s, config.COLOR_CONTACT_BIO,
                               [int(v) for v in to_screen(buoy["x"], buoy["y"])], 3, 1)
        ship = frame["ship"]
        sx, sy = to_screen(ship["x"], ship["y"])
        pygame.draw.circle(s, OWN_COLOR, (int(sx), int(sy)), 6)
        rad = math.radians(ship["course"])
        pygame.draw.line(s, OWN_COLOR, (sx, sy), (sx + 16 * math.sin(rad), sy - 16 * math.cos(rad)), 2)
        for sub in frame["subs"]:
            if not sub["hostile"]:
                continue
            bx, by = to_screen(sub["x"], sub["y"])
            color = config.COLOR_TEXT_DIM if sub["sunk"] else config.COLOR_CONTACT_UBOOT
            pygame.draw.polygon(s, color, [(bx, by - 8), (bx + 8, by), (bx, by + 8), (bx - 8, by)], 2)
            layout.blit_line(s, message(recorder.prefix + "sub_label", sub=sub["id"], depth=sub["depth"]),
                             (int(bx) + 10, int(by) - 9, 140, 18), color, size=13)
        for row in frame["known"]:
            color = config.COLOR_WARN
            if row["x"] is not None:
                kx, ky = to_screen(row["x"], row["y"])
                pygame.draw.line(s, color, (kx - 6, ky - 6), (kx + 6, ky + 6), 2)
                pygame.draw.line(s, color, (kx - 6, ky + 6), (kx + 6, ky - 6), 2)
                layout.blit_line(s, row["label"], (int(kx) + 8, int(ky) + 2, 80, 16), color, size=12)
            else:
                rad = math.radians(row["bearing"])
                length = 0.3 * min(MAP.w, MAP.h)
                pygame.draw.line(s, color, (sx, sy),
                                 (sx + length * math.sin(rad), sy - length * math.cos(rad)), 1)
        for weapon in frame["own_weapons"]:
            pygame.draw.circle(s, config.COLOR_FLIGHT,
                               [int(v) for v in to_screen(weapon["x"], weapon["y"])], 3)
        for weapon in frame["enemy_weapons"]:
            pygame.draw.circle(s, config.COLOR_DANGER,
                               [int(v) for v in to_screen(weapon["x"], weapon["y"])], 3)
        # Aircraft: the frigate's own on its debrief, the hunters on the boat's.
        asset_color = OWN_COLOR if recorder.prefix == "debrief." else config.COLOR_DANGER
        for asset in frame["assets"]:
            ax, ay = to_screen(asset["x"], asset["y"])
            pygame.draw.rect(s, asset_color, (int(ax) - 4, int(ay) - 4, 8, 8), 1)
        # Shots, pings, hits and sinkings flash where they happened.
        for event, k in debrief_replay.flashes(recorder.events, frame["t"],
                                              game.debrief_replay.speed):
            fx, fy = to_screen(*debrief_replay.flash_position(event, frame))
            color = EVENT_COLORS[event["kind"]]
            fade = tuple(int(b + (c - b) * (1.0 - k)) for c, b in zip(color, config.COLOR_GEO_BG))
            pygame.draw.circle(s, fade, (int(fx), int(fy)), int(8 + 34 * k), 2)
            if k < 0.25:
                pygame.draw.circle(s, color, (int(fx), int(fy)), 5)
    layout.blit_line(s, message(recorder.prefix + "legend", step=f"{step:g}"), (MAP.x, 42, MAP.w, 20),
                     config.COLOR_TEXT_DIM, size=13, align="right")


def _draw_side(game, s, recorder, frame) -> None:
    pygame.draw.rect(s, config.COLOR_PANEL_BG, SIDE)
    pygame.draw.rect(s, config.COLOR_GRID, SIDE, 1)
    metrics = recorder.metrics()

    def at(value):
        return _clock(value) if value is not None else localize("debrief.never")

    lines = [
        message(recorder.prefix + "metric.first_contact", time=at(metrics["first_contact_t"])),
        message(recorder.prefix + "metric.first_fix", time=at(metrics["first_fix_t"])),
        message(recorder.prefix + "metric.classified", time=at(metrics["classified_t"])),
        message(recorder.prefix + "metric.shots", shots=metrics["shots"], sunk=metrics["sunk"]),
        (message(recorder.prefix + "metric.error", error=f"{metrics['mean_error_nm']:.1f}")
         if metrics["mean_error_nm"] is not None else message(recorder.prefix + "metric.no_error")),
        message(recorder.prefix + "metric.missed", count=metrics["missed"]),
    ]
    y = SIDE.y + 10
    for line in lines:
        layout.blit_line(s, line, (SIDE.x + 12, y, SIDE.w - 24, 24), config.COLOR_TEXT, size=16)
        y += 26
    current = (message(recorder.prefix + "error_now", error=f"{min(frame['errors']):.1f}")
               if frame["errors"] else message(recorder.prefix + "no_contact_now"))
    layout.blit_line(s, current, (SIDE.x + 12, y, SIDE.w - 24, 24), config.COLOR_WARN, size=16)
    y += 32
    pygame.draw.line(s, config.COLOR_GRID, (SIDE.x + 8, y), (SIDE.right - 8, y))
    y += 8
    if getattr(game, "debrief_report_open", False):
        # The optional language model's after-action report (key B).
        side = "uboot" if recorder.prefix != "debrief." else "frigate"
        layout.blit_line(s, "debrief.report", (SIDE.x + 12, y, SIDE.w - 24, 24),
                         config.COLOR_TEXT, size=17)
        state = game.llm_report(side) if game.llm_active() or game.llm_report(side) else None
        if state is not None:
            state = dict(state, scroll=game.debrief_report_scroll)
        llm_text.draw_state(s, (SIDE.x + 12, y + 28, SIDE.w - 24, SIDE.bottom - y - 36),
                            state, size=15)
        return
    layout.blit_line(s, "debrief.events", (SIDE.x + 12, y, SIDE.w - 24, 24),
                     config.COLOR_TEXT, size=17)
    y += 28
    rows = max(1, (SIDE.bottom - 8 - y) // 24)
    events = recorder.events
    past = [i for i, event in enumerate(events) if event["t"] <= frame["t"]]
    current_index = past[-1] if past else -1
    start = max(0, min(current_index - rows // 2, len(events) - rows))
    for i, event in enumerate(events[start:start + rows], start):
        color = EVENT_COLORS[event["kind"]]
        if i > current_index:
            color = config.COLOR_TEXT_DIM
        prefix = ">" if i == current_index else " "
        layout.blit_line(s, f"{prefix}{_clock(event['t'])} " + event_text(event, recorder.prefix),
                         (SIDE.x + 8, y, SIDE.w - 16, 22), color, size=14)
        y += 24


def _draw_timeline(s, recorder, frame) -> None:
    pygame.draw.rect(s, config.COLOR_PANEL_BG, TIMELINE)
    pygame.draw.rect(s, config.COLOR_GRID, TIMELINE, 1)
    end = max(1e-6, recorder.frames[-1]["t"])
    for event in recorder.events:
        x = TIMELINE.x + int(event["t"] / end * (TIMELINE.w - 1))
        pygame.draw.line(s, EVENT_COLORS[event["kind"]], (x, TIMELINE.y + 4),
                         (x, TIMELINE.bottom - 4), 2)
    x = TIMELINE.x + int(frame["t"] / end * (TIMELINE.w - 1))
    pygame.draw.line(s, config.COLOR_TEXT, (x, TIMELINE.y - 4), (x, TIMELINE.bottom + 4), 3)

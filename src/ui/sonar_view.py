"""Read-only sonar instruments. All plots use receiver data or observations."""

import math
from collections import OrderedDict
from functools import lru_cache

import numpy as np
import pygame

from src.core import config
from src.core.i18n import (display_message, display_value, localized, localize,
                            message as structured_message)
from src.sonar import analysis_tools, class_library, tma_operator
from src.ui import layout
from src.ui import observations
from src.ui import profile_cursor


NAVY = (6, 13, 25)
PANEL = (10, 22, 37)
GRID = (24, 49, 65)
DIM = (119, 151, 169)
TEXT = (211, 229, 233)
CYAN = (79, 224, 202)
AMBER = (244, 190, 97)
PHOSPHOR_PALETTES = {
    "green": (68, 255, 154),
    "amber": (255, 184, 62),
    "cyan": CYAN,
}
PAGES = ("BROADBAND", "LOFAR", "DEMON", "TMA", "UMWELT/FUSION", "ACTIVE")
ACTIVE_HISTORY_WINDOW_S = 120.0
DEMON_DISPLAY_MAX_HZ = 50.0
_WATERFALL_CACHE = OrderedDict()
_WATERFALL_CACHE_SCREEN = None



def _sonar_observer(game):
    """Listening platform of the active sonar workstation (frigate or boat)."""
    observer = getattr(game, "sonar_observer", None)
    return getattr(game, "ship", None) if observer is None else observer

def message(key, **values):
    """A structured message: localized at draw time so layouts can abbreviate."""
    return structured_message(key, **values)


def _observed_bearing(observation) -> float:
    return observations.bearing(observation)


def _bearing_line(game, bearing) -> str:
    return layout.format_bearing_pair(
        bearing, getattr(_sonar_observer(game), "course", 0.0))


def _panels(game, page):
    station = pygame.Rect(config.STATION_RECT)
    # Tightened top/bottom margins (was +73/-124): the larger operational
    # font floor needs a few extra px in `details` so worst-case content
    # (e.g. a fully evidenced TMA solution) never clips.
    body = pygame.Rect(station.x + 12, station.y + 43,
                       station.w - 24, station.h - 68)
    rail_w = min(350, max(240, round(body.w * .28)))
    main = pygame.Rect(body.x, body.y, body.w - rail_w - 12, body.h)
    rail = pygame.Rect(main.right + 12, body.y, rail_w, body.h)
    # Reserve three full contact rows on every page. Long interpretation notes
    # belong in the bounded tooltip rather than displacing operational data.
    contact_min_h = 33 + 3 * 43
    details = pygame.Rect(rail.x, rail.y, rail.w,
                          max(1, rail.h - contact_min_h - 8))
    contacts = pygame.Rect(rail.x, details.bottom + 8, rail.w,
                           rail.bottom - details.bottom - 8)
    return main, details, contacts


def _waterfall_plot(panel, page):
    top = panel.y + (105 if page == 1 else 61)
    return pygame.Rect(panel.x + 57, top, panel.w - 83,
                       panel.bottom - 47 - top)


def _history_for_page(sonar, page):
    if page == 0 and getattr(sonar, "broadband_long_history", None):
        return sonar.broadband_long_history, sonar.broadband_long_times, \
            config.SONAR_BROADBAND_LONG_ROWS
    if page == 0:
        return (getattr(sonar, "broadband_history", []),
                getattr(sonar, "history_times", []), config.LOFAR_HISTORY_COLS)
    return (getattr(sonar, "lofar_history", []),
            getattr(sonar, "lofar_times", []), config.LOFAR_HISTORY_COLS)


def _visible_contacts(game, rect):
    contacts = sorted(game.sonar.active_contacts(), key=lambda item: item.id)
    capacity = max(1, (rect.h - 33) // 43)
    selected = getattr(game, "selected_contact", None)
    index = next((i for i, item in enumerate(contacts) if item is selected), 0)
    start = max(0, min(index - capacity // 2, len(contacts) - capacity))
    return contacts, start, contacts[start:start + capacity]


def _visible_echoes(game, rect):
    latest = {}
    for echo in active_echoes(game.sonar, getattr(game, "sim_t", 0.0)):
        latest[echo.get("contact_id")] = echo
    capacity = max(1, (rect.h - 33) // 43)
    return list(reversed(list(latest.values())[-capacity:])), len(latest)


def _list_rows(game, rect, page):
    """Return the exact visible row payloads and painted hit rectangles."""
    if page == 5:
        rows, total = _visible_echoes(game, rect)
    else:
        _, _, rows = _visible_contacts(game, rect)
        total = None
    return [(item, pygame.Rect(rect.x + 5, rect.y + 32 + index * 43,
                               rect.w - 10, 41))
            for index, item in enumerate(rows)], total


def _array_readout(game):
    """Array in use; a towed/variable-depth array adds its state until ready."""
    sonar = game.sonar
    mode = getattr(game, "sonar_mode", "BOW")
    name = display_value("array", mode)
    status = (_vds_status(sonar) if mode == "VDS" else None) or (
        _tow_status(sonar, getattr(_sonar_observer(game), "speed", 0.0))
        if mode != "BOW" else None)
    if status is None or status["available"]:
        return name
    return f"{name} {status['payout_percent']:.0f}%"


def sonar_geometry(game, page=None):
    """Return the canonical rectangles used by both sonar draw and hit paths."""
    layout.configure_for(game)
    station = pygame.Rect(config.STATION_RECT)
    page = int(getattr(game, "sonar_page", 0) if page is None else page) % len(PAGES)
    tab_x = station.x + 348
    tab_w = max(50, (station.w - 362) // len(PAGES))
    tabs = [pygame.Rect(tab_x + i * tab_w, station.y + 9, tab_w - 5, 27)
            for i in range(len(PAGES))]
    main, details, contacts = _panels(game, page)
    sonar = game.sonar
    on_off = lambda flag: localize("ui.on" if flag else "ui.off")
    array = ("SHIFT+B", "sonar.footer.array", "", _array_readout(game))
    gain = ("I/O", "sonar.footer.gain", "", f"{getattr(sonar, 'gain_db', 0):+.0f} dB")
    band = ("F/D", "sonar.footer.band_filter", "",
            f"{getattr(sonar, 'band_low_hz', 0):.0f}-{getattr(sonar, 'band_high_hz', 300):.0f} Hz")
    notch = ("N", "sonar.footer.notch", "", on_off(getattr(sonar, "notch_enabled", False)))
    audio = ("J", "sonar.footer.audio", "", on_off(getattr(game, "sonar_audio_enabled", False)))
    # One row of at most four main keys per page; the rest lives in F1.
    specs = ((array, "array"), (gain, "gain"),
             (("SPACE", "sonar.footer.peak", "", on_off(getattr(sonar, "peak_hold", False))), "peak"),
             (audio, "audio"))
    tools = getattr(game, "sonar_tools", None)
    if page in (1, 2) and tools is not None:
        # Analysis pages: the operator's cursor tools replace peak/audio.
        cursor = tools.lofar_cursor_hz if page == 1 else tools.demon_cursor_hz
        harmonic = _selected_harmonic(game)
        mark = (structured_message("sonar.footer.demon_marks",
                                   shaft="--" if tools.shaft_hz is None else f"{tools.shaft_hz:.1f}",
                                   blade="--" if tools.blade_hz is None else f"{tools.blade_hz:.1f}")
                if page == 2 else
                f"{harmonic:.1f} Hz" if harmonic is not None else localize("ui.off"))
        specs = ((("K", "sonar.footer.mark", "", mark), "harmonic"),
                 (("Z/X", "sonar.footer.cursor", "", f"{cursor:.1f} Hz"), "cursor"),
                 (("Q", "sonar.footer.integration", "", f"{tools.integration_s} s"), "integration"),
                 (band, "band_filter") if page == 1 else (gain, "gain"))
    elif page in (1, 4):
        specs = ((array, "array"), (gain, "gain"), (band, "band_filter"), (notch, "notch"))
    contact = getattr(game, "selected_contact", None)
    if page == 3 and contact is not None and hasattr(game, "tma_hypothesis"):
        hypothesis = game.tma_hypothesis(contact)
        evaluation = game.tma_evaluation(contact)
        specs = (
            (("K", "sonar.footer.tma_accept", "",
              "--" if evaluation is None else f"{evaluation['fit']:.0%}"), "tma_accept"),
            (("Z/X", "sonar.footer.tma_course", "", f"{hypothesis.course:05.1f}\u00b0"), "cursor"),
            (("^Z/^X", "sonar.footer.tma_speed", "", f"{hypothesis.speed_kn:.1f} kn"), "cursor"),
            (("Q", "sonar.footer.tma_range", "", f"{hypothesis.range_nm:.1f} NM"), "cursor"))
    footer = []
    width = (station.w - 28) // len(specs)
    for index, (spec, action) in enumerate(specs):
        rect = pygame.Rect(station.x + 14 + index * width,
                           station.bottom - 22, width - 6, 19)
        footer.append(dict(rect=rect, action=action, text=spec, safe=True))
    return dict(station=station, tabs=tabs, main=main, details=details,
                contacts=contacts, footer=footer)


def sonar_click_target(game, pos):
    """Resolve only explicitly safe sonar actions; return no simulation object."""
    if pos is None:
        return None
    geometry = sonar_geometry(game)
    if not geometry["station"].collidepoint(pos):
        return None
    for page, rect in enumerate(geometry["tabs"]):
        if rect.collidepoint(pos):
            return {"action": "page_set", "value": page, "safe": True}
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    plot = _waterfall_plot(geometry["main"], page)
    if page == 0 and plot.collidepoint(pos):
        bearing = (pos[0] - plot.x) / max(1, plot.w - 1) * 360.0
        contacts = list(getattr(game.sonar, "active_contacts", lambda: ())())
        threshold = max(3.0, float(getattr(game.sonar, "beam_width_deg", 0.0)) / 2.0)
        nearest = min(
            contacts,
            key=lambda item: abs((_observed_bearing(item) - bearing + 180.0) % 360.0 - 180.0),
            default=None,
        )
        if nearest is not None:
            separation = abs((_observed_bearing(nearest) - bearing + 180.0) % 360.0 - 180.0)
            if separation <= threshold:
                return {"action": "contact_listen", "value": nearest.id, "safe": True}
        return {"action": "listen_bearing", "value": bearing % 360.0, "safe": True}
    if geometry["contacts"].collidepoint(pos):
        for item, rect in _list_rows(game, geometry["contacts"], page)[0]:
            if rect.collidepoint(pos):
                action = "echo" if page == 5 else "contact"
                value = item.get("contact_id") if page == 5 else item.id
                return {"action": action, "value": value, "safe": True}
    for segment in geometry["footer"]:
        if segment["rect"].collidepoint(pos):
            return {key: segment[key] for key in ("action", "safe")}
    return None


@localized
def sonar_hit_target(game, pos):
    """Return context for a plotted receiver datum or displayed observation."""
    layout.configure_for(game)
    station = pygame.Rect(config.STATION_RECT)
    if pos is None or not station.collidepoint(pos):
        return None
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    sonar = game.sonar
    geometry = sonar_geometry(game, page)
    main, details, contacts_rect = (geometry["main"], geometry["details"],
                                    geometry["contacts"])
    for index, tab in enumerate(geometry["tabs"]):
        if tab.collidepoint(pos):
            return layout.tooltip_payload(
                message("sonar.tooltip.page", page=display_value("sonar_page", PAGES[index])),
                "sonar.tooltip.safe_page", target_id=f"sonar:tab:{index}")
    for segment in geometry["footer"]:
        if segment["rect"].collidepoint(pos):
            return layout.tooltip_payload(
                segment["text"][1], "sonar.tooltip.safe_control",
                target_id=f"sonar:action:{segment['action']}")
    if contacts_rect.collidepoint(pos):
        rows = _list_rows(game, contacts_rect, page)[0]
        if page == 5:
            for echo, rect in rows:
                if rect.collidepoint(pos):
                    break
            else:
                echo = None
            if echo is not None:
                return layout.tooltip_payload(
                    message("sonar.tooltip.echo_title", contact=echo.get('contact_id', '--')),
                    _bearing_line(game, echo["bearing"]),
                    message("sonar.tooltip.range", range=f"{float(echo['range_nm']):.2f}"),
                    message("sonar.tooltip.uncertainty_age", uncertainty=f"{float(echo.get('range_sigma_nm', 0)):.2f}", age=f"{echo['age_s']:.1f}"),
                    message("sonar.tooltip.active_source", mode=echo.get('mode', '--')),
                    target_id=f"sonar:echo:{echo.get('contact_id', '')}")
        else:
            for contact, rect in rows:
                if rect.collidepoint(pos):
                    break
            else:
                contact = None
            if contact is not None:
                label = display_value("classification",
                                      getattr(contact, "player_class", None))
                return layout.tooltip_payload(
                    message("sonar.tooltip.contact_title",
                            contact=observations.contact_display_id(game, contact)),
                    observations.format_bearing_pair(
                        contact, _sonar_observer(game)),
                    message("observation.bearing_uncertainty", uncertainty=f"{observations.bearing_uncertainty(contact):.1f}")
                    if observations.bearing_uncertainty(contact) is not None else None,
                    message("sonar.tooltip.classification", classification=label),
                    message("sonar.tooltip.opz_release",
                            state=localize("sonar.release.released"
                                           if getattr(contact, "released_to_opz", False)
                                           else "sonar.release.private")),
                    message("sonar.tooltip.level_confidence", level=f"{getattr(contact, 'snr', -99):+.1f}", confidence=f"{getattr(contact, 'confidence', 0):.0%}"),
                    message("sonar.tooltip.track_age", age=f"{max(0, game.sim_t - getattr(contact, 'last_seen', 0)):.0f}"),
                    message("observation.fix_age", age=f"{max(0, game.sim_t - contact.range_seen):.0f}")
                    if getattr(contact, "range_est", None) is not None
                    and getattr(contact, "range_seen", None) is not None else None,
                    target_id=f"sonar:contact:{contact.id}")
        return None
    if details.collidepoint(pos):
        return layout.tooltip_payload(
            message("sonar.evaluation"), message("sonar.tooltip.page", page=display_value('sonar_page', PAGES[page])),
            message("sonar.evaluation_caption"),
            message("control.sonar_page"),
            target_id=f"sonar:details:{page}")
    if not main.collidepoint(pos):
        if station.y + 40 <= pos[1] < station.y + 70:
            return layout.tooltip_payload(
                message("sonar.control_status"),
                message("sonar.tooltip.array", array=display_value("array", getattr(game, 'sonar_mode', 'BOW'))),
                message("sonar.tooltip.listen_bearing", bearing=_bearing_line(
                    game, getattr(sonar, "listen_bearing", 0))),
                message("sonar.tooltip.gain_filter", gain=f"{getattr(sonar, 'gain_db', 0):+.0f}", low=f"{getattr(sonar, 'band_low_hz', 0):.0f}", high=f"{getattr(sonar, 'band_high_hz', 300):.0f}"),
                message("control.sonar"),
                target_id="sonar:controls")
        return None
    if page in (0, 1):
        plot = _waterfall_plot(main, page)
        if not plot.collidepoint(pos):
            return None
        axis = (pos[0] - plot.x) / max(1, plot.w - 1)
        rows, times, history_rows = _history_for_page(sonar, page)
        live = page == 1 and not len(rows)
        if live:
            spectrum = getattr(getattr(sonar, "receiver", None), "spectrum", [])
            rows = [spectrum] if len(spectrum) else []
        count = len(rows) if live else max(history_rows, len(rows))
        row = len(rows) - 1 - int((pos[1] - plot.y) * count / plot.h)
        if not 0 <= row < len(rows) or not len(rows[row]):
            return layout.tooltip_payload(
                message("sonar.tooltip.broadband_bin" if page == 0 else "sonar.tooltip.lofar_bin"),
                message("sonar.no_receiver_data"),
                target_id=f"sonar:empty-history:{page}")
        stamp = (message("sonar.tooltip.sim_time", time=f"{times[row]:.1f}")
                 if row < len(times) else None)
        if page == 0:
            bin_count = len(rows[row])
            bin_index = round(axis * bin_count) % bin_count
            bearing = bin_index * (360.0 / bin_count)
            level = float(np.clip(_circular_broadband(rows[row], plot.w)[
                int(pos[0] - plot.x)] * 10 ** (getattr(sonar, "gain_db", 0) / 20), 0, 1))
            return layout.tooltip_payload(
                message("sonar.tooltip.broadband_bin"), _bearing_line(game, bearing),
                message("sonar.tooltip.relative_level", level=f"{level:.3f}"),
                stamp,
                message("tooltip.omni_sample"),
                target_id=f"sonar:broadband:{bearing:.1f}")
        frequency = axis * config.LOFAR_FMAX_HZ
        processed = _process_lofar_rows(
            np.asarray([rows[row]], dtype=float), _waterfall_controls(game, page),
            getattr(sonar, "process_lofar_column", None) is not None)
        level = float(_linear_lofar(processed[0], plot.w)[int(pos[0] - plot.x)])
        bearings = getattr(sonar, "lofar_bearings", [])
        beam = (bearings[row] if row < len(bearings) else
                getattr(sonar, "listen_bearing", 0) if live else None)
        return layout.tooltip_payload(
            message("sonar.tooltip.lofar_bin"), message("sonar.tooltip.frequency_level", frequency=f"{frequency:.1f}", level=f"{level:.3f}"),
            stamp,
            message("sonar.tooltip.beam_source", bearing=_bearing_line(game, beam))
            if beam is not None else None,
            target_id=f"sonar:lofar:{frequency:.1f}")
    if page == 2:
        plot = pygame.Rect(main.x + 57, main.y + 62, main.w - 83,
                           main.h - 109)
        if not plot.collidepoint(pos):
            return None
        frequency = (pos[0] - plot.x) / max(1, plot.w - 1) * DEMON_DISPLAY_MAX_HZ
        spectrum = getattr(getattr(sonar, "receiver", None),
                           "demon_spectrum", [])
        index = min(len(spectrum) - 1, max(0, round(frequency) - 1)) \
            if len(spectrum) else 0
        level = float(spectrum[index]) if len(spectrum) else 0.0
        return layout.tooltip_payload(
            message("sonar.tooltip.demon_line"), message("sonar.tooltip.frequency_level", frequency=f"{frequency:.1f}", level=f"{level:.3f}"),
            message("sonar.envelope_source"),
            target_id=f"sonar:demon:{frequency:.1f}")
    if page == 3:
        contact = getattr(game, "selected_contact", None)
        track = getattr(sonar, "_tracks", {}).get(
            getattr(contact, "target_id", None))
        points = list(getattr(track, "pts", []))
        if not points:
            return None
        plot, _, _, xy = _tma_plot(main, points)
        index = min(range(len(xy)), key=lambda i:
                    (xy[i][0] - pos[0]) ** 2 + (xy[i][1] - pos[1]) ** 2)
        if not plot.collidepoint(pos) or pygame.Vector2(xy[index]).distance_to(pos) > 8:
            return None
        point = points[index]
        return layout.tooltip_payload(
            message("sonar.tma_point"),
            layout.format_bearing_pair(point.bearing,
                                       getattr(point, "fcourse", 0.0)),
            message("sonar.tooltip.sim_time", time=f"{float(point.t):.1f}"),
            message("sonar.tooltip.recorded_course", course=f"{float(getattr(point, 'fcourse', 0)) % 360:05.1f}"),
            message("sonar.tma_source"),
            target_id=f"sonar:tma:{float(point.t):.1f}")
    if page == 5:
        echoes = active_echoes(sonar, getattr(game, "sim_t", 0.0))
        if echoes:
            ascope, polar, max_range = _active_geometry(main, echoes)
            if polar.collidepoint(pos):
                echo = min(echoes, key=lambda item: pygame.Vector2(
                    _echo_point(polar, max_range, item)).distance_to(pos))
                distance = pygame.Vector2(_echo_point(polar, max_range, echo)).distance_to(pos)
            elif ascope.collidepoint(pos):
                latest = {item.get("contact_id"): item for item in echoes}
                echo = min(latest.values(), key=lambda item: abs(
                    _ascope_point(ascope, max_range, item)[0] - pos[0]))
                x, y = _ascope_point(ascope, max_range, echo)
                distance = max(abs(x - pos[0]), y - pos[1])
            else:
                return None
            if distance > 8:
                return None
            return layout.tooltip_payload(
                message("sonar.tooltip.active_echoes", count=len(echoes)),
                message("sonar.tooltip.echo_title", contact=echo.get('contact_id', '--')),
                message("sonar.line.echo_age_mode", age=f"{echo['age_s']:.1f}", mode=echo.get('mode', '--')),
                _bearing_line(game, echo["bearing"]),
                message("sonar.tooltip.range_sigma", range=f"{float(echo['range_nm']):.2f}", sigma=f"{float(echo.get('range_sigma_nm', 0)):.2f}"),
                message("sonar.active_source"),
                target_id=f"sonar:active-plot:{echo.get('contact_id')}:{echo['t']}")
    return layout.tooltip_payload(message("sonar.tooltip.plot"),
                                  message("sonar.tooltip.page", page=display_value('sonar_page', PAGES[page])),
                                  message("sonar.displayed_data"),
                                  target_id=f"sonar:plot:{page}")


def _text(screen, text, rect, color=TEXT, size=14, align="left"):
    """One readable line, ellipsized rather than shrunk into microtext."""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    font = layout.font(size)
    text = layout.fit_line(text, font, rect.w)
    x = rect.x
    if align == "right":
        x = rect.right - font.size(text)[0]
    elif align == "center":
        x += (rect.w - font.size(text)[0]) // 2
    with layout.clip_to(screen, rect):
        image = font.render(text, True, color)
        rendered = image.get_rect(topleft=(x, rect.y))
        layout.record_text(text, rendered, rect, image)
        screen.blit(image, rendered)


def waterfall_surface(rows, width, height, gain_db=0.0, *, black_level=0.0,
                      contrast=1.0, palette="cyan"):
    """Oldest-first rows become a bitmap with newest at TOP; x is bin order.

    Zero input stays dark. Gain changes intensity, never time or frequency.
    The small row bitmap is scaled once, not drawn as thousands of rectangles.
    """
    width, height = max(1, int(width)), max(1, int(height))
    pixels = waterfall_pixels(rows, gain_db, black_level=black_level,
                              contrast=contrast, palette=palette)
    if pixels is None:
        surface = pygame.Surface((width, height))
        surface.fill(NAVY)
        return surface
    small = pygame.surfarray.make_surface(pixels.transpose(1, 0, 2))
    return pygame.transform.scale(small, (width, height))


def waterfall_pixels(rows, gain_db=0.0, *, black_level=0.0, contrast=1.0,
                     palette="cyan", colors=None):
    """Pure phosphor mapping behind waterfall_surface: rows x bins x RGB.

    Shared with the packaged contact-analysis images so their traces look
    exactly like the station display; ``colors=(empty, full)`` swaps only the
    end colours (the printed unit reference uses white paper and dark ink).
    Returns None for empty input.
    """
    values = np.asarray(rows, dtype=np.float32)
    if values.size == 0:
        return None
    values = np.nan_to_num(values, nan=0.0, posinf=1.0, neginf=0.0)
    values = np.clip(values[::-1] * 10.0 ** (gain_db / 20.0), 0.0, 1.0)
    black_level = float(np.clip(black_level, 0.0, .8))
    contrast = float(np.clip(contrast, .5, 4.0))
    values = np.clip((values - black_level) / max(.01, 1.0 - black_level)
                     * contrast, 0.0, 1.0)
    # CRT-like persistence: the newest line is bright while older energy
    # remains visible as a bounded fading trail.
    persistence = np.linspace(1.0, .22, len(values), dtype=np.float32)
    values *= persistence[:, None]
    # A navy-to-phosphor ramp leaves faint receiver noise visible, not invented.
    low, high = colors or (NAVY, PHOSPHOR_PALETTES.get(palette, CYAN))
    low, high = np.asarray(low), np.asarray(high)
    return (low + values[..., None] ** .72 * (high - low)).astype(np.uint8)


def _circular_broadband(row, width):
    """Interpolate 180 circular bearing bins, joining 358 degrees to north."""
    width = max(1, int(width))
    values = np.asarray(row, dtype=float)
    if values.size == 0:
        return np.zeros(width)
    source = np.arange(values.size + 1, dtype=float)
    wrapped = np.concatenate((values, values[:1]))
    target = np.linspace(0.0, float(values.size), width)
    return np.interp(target, source, wrapped)


def _linear_lofar(row, width):
    """Interpolate the existing 1/2/5 Hz bins onto an honest linear Hz axis."""
    if len(row) == 0:
        return np.zeros(width)
    frequencies = _lofar_frequencies(len(row))
    return np.interp(np.linspace(0.0, config.LOFAR_FMAX_HZ, width),
                     frequencies, row)


@lru_cache(maxsize=8)
def _lofar_frequencies(size):
    return np.asarray([config.lofar_bin_freq(i) for i in range(size)])


def _process_lofar_rows(raw, controls, apply_filters=True):
    """Vectorized equivalent of Sonar.process_lofar_column over all rows."""
    gain_db, band_low, band_high, notch_enabled, ship_speed = controls[:5]
    operator_notch = controls[5] if len(controls) > 5 else None
    gain = 10.0 ** (gain_db / 20.0)
    processed = np.clip(raw * gain, 0.0, 1.0)
    if not apply_filters or raw.shape[-1] == 0:
        return processed
    frequencies = _lofar_frequencies(raw.shape[-1])
    in_band = (frequencies >= band_low) & (frequencies <= band_high)
    processed[:, ~in_band] = 0.0
    if notch_enabled:
        shaft = 10.0 + 1.9 * ship_speed
        notch = in_band & (np.abs(frequencies - shaft) < 5.0)
        processed[:, notch] = np.clip(raw[:, notch] * gain * 0.15, 0.0, 1.0)
    if operator_notch is not None:
        notch = in_band & (np.abs(frequencies - operator_notch) < 2.5)
        processed[:, notch] = np.clip(raw[:, notch] * gain * 0.15, 0.0, 1.0)
    return processed


def _waterfall_controls(game, page):
    sonar = game.sonar
    filters = page == 1 and getattr(sonar, "process_lofar_column", None) is not None
    notch = filters and getattr(sonar, "notch_enabled", False)
    tools = getattr(game, "sonar_tools", None)
    return (getattr(sonar, "gain_db", 0.0),
            getattr(sonar, "band_low_hz", 0.0) if filters else 0.0,
            getattr(sonar, "band_high_hz", 300.0) if filters else 300.0,
            notch, getattr(_sonar_observer(game), "speed", 0.0) if notch else 0.0,
            getattr(sonar, "operator_notch_hz", None) if filters else None,
            getattr(tools, "integration_s", 2) if page in (1, 2) else 2)


def _display_controls(game):
    return (float(getattr(game, "sonar_display_black", 0.0)),
            float(getattr(game, "sonar_display_contrast", 1.6)),
            str(getattr(game, "sonar_display_palette", "green")),
            float(getattr(game, "sonar_display_history", 1.0)))


def _draw_display_status(game, panel):
    black, contrast, palette, history = _display_controls(game)
    key = ("sonar.line.display_history" if history < 0.995
           else "sonar.line.display")
    value = message(key, palette=message(f"sonar.palette.{palette.lower()}"),
                    contrast=f"{contrast:.1f}", black=f"{black:.2f}",
                    history=f"{history * 100:.0f}")
    _text(game.screen, value, (panel.right - 456, panel.y + 11, 440, 18),
          DIM, 12, "right")


def _waterfall(game, page, rect):
    global _WATERFALL_CACHE_SCREEN
    if game.screen is not _WATERFALL_CACHE_SCREEN:
        _WATERFALL_CACHE.clear()
        _WATERFALL_CACHE_SCREEN = game.screen
    sonar = game.sonar
    receiver = getattr(sonar, "receiver", None)
    source_rows, _, history_rows = _history_for_page(sonar, page)
    history_fraction = _display_controls(game)[3]
    visible_rows = max(1, round(history_rows * history_fraction))
    rows = source_rows[-visible_rows:]
    history_rows = visible_rows
    live_fallback = not len(rows) and page == 1
    # No focus gate: an empty history may still have a live receiver spectrum.
    if not len(rows) and page == 1:
        current = getattr(receiver, "spectrum", [])
        rows = [current] if len(current) else []
    controls = _waterfall_controls(game, page)
    if live_fallback:
        history_token = (id(rows[0]), len(rows[0])) if rows else (None, 0)
    else:
        history_token = (id(source_rows), len(source_rows),
                         id(source_rows[0]) if len(source_rows) else None,
                         id(source_rows[-1]) if len(source_rows) else None)
    display = _display_controls(game)[:3]
    key = (id(sonar), page, rect.size, getattr(receiver, "sequence", None),
           controls, display, history_fraction, history_token)
    cached = _WATERFALL_CACHE.get(key)
    if cached is None:
        raw = np.asarray(rows, dtype=float)
        processed = rows
        if page == 1 and len(rows):
            process = getattr(sonar, "process_lofar_column", None)
            # Operator integration: each row averages its last N seconds.
            raw = analysis_tools.integrate_rows(raw, controls[6])
            processed = _process_lofar_rows(raw, controls, process is not None)
            processed = np.asarray([_linear_lofar(row, rect.w) for row in processed])
        elif page == 0 and len(rows):
            processed = np.asarray([_circular_broadband(row, rect.w)
                                    for row in raw])
        # Fixed time scale from the first sample: empty history stays below it.
        bitmap = processed
        if (not live_fallback and len(processed)
                and len(processed) < history_rows):
            bitmap = np.concatenate((np.zeros((history_rows - len(processed),
                                               len(processed[0]))), processed))
        surface = waterfall_surface(
            bitmap, *rect.size, gain_db=controls[0] if page == 0 else 0.0,
            black_level=display[0], contrast=display[1], palette=display[2])
        cached = (surface, processed)
        _WATERFALL_CACHE[key] = cached
        while len(_WATERFALL_CACHE) > 4:
            _WATERFALL_CACHE.popitem(last=False)
    _WATERFALL_CACHE.move_to_end(key)
    game.screen.blit(cached[0], rect)
    return cached[1]


def _grid(screen, rect, xmax, unit):
    divisions = 5 if xmax == DEMON_DISPLAY_MAX_HZ else 6
    for index in range(divisions + 1):
        x = rect.x + round(index * (rect.w - 1) / divisions)
        pygame.draw.line(screen, GRID, (x, rect.y), (x, rect.bottom - 1))
        label = f"{index * xmax / divisions:.0f}"
        _text(screen, label, (x - 28, rect.bottom + 5, 56, 20), DIM, 13, "center")
    _text(screen, unit, (rect.right - 180, rect.bottom + 25, 180, 19), DIM, 13, "right")
    pygame.draw.rect(screen, GRID, rect, 1)


def _trace(screen, rect, values, color=CYAN):
    if len(values) < 2:
        return
    values = np.clip(np.nan_to_num(values), 0, 1)
    points = [(rect.x + round(i * (rect.w - 1) / (len(values) - 1)),
               rect.bottom - 1 - round(float(v) * (rect.h - 1)))
              for i, v in enumerate(values)]
    with layout.clip_to(screen, rect):
        pygame.draw.lines(screen, color, False, points, 1)


PEAK_LABEL_W = 40


def spectrum_peaks(values, frequencies, limit=8, min_separation_hz=0.0):
    """Prominent local maxima of a displayed spectrum as ``(hz, level)``.

    A peak must stand clearly above the median floor and its own
    neighbourhood; the frequency is refined by a parabola through the three
    bins around it. Strongest first, thinned so labels cannot overlap, then
    returned in frequency order. Pure and bounded (``limit``).
    """
    v = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0,
                      posinf=0.0, neginf=0.0)
    f = np.asarray(frequencies, dtype=float)
    if v.size < 3 or f.size != v.size or limit <= 0:
        return []
    top = float(v.max())
    floor = float(np.median(v))
    span = top - floor
    if top < .03 or span <= 1e-6:
        return []
    threshold = max(floor + .25 * span, floor * 1.6, .03)
    inner = v[1:-1]
    local = np.flatnonzero((inner > v[:-2]) & (inner >= v[2:])
                           & (inner >= threshold)) + 1
    window = 4
    candidates = []
    for i in local:
        left = v[max(0, i - window):i].min()
        right = v[i + 1:i + 1 + window].min()
        if v[i] - max(left, right) < .1 * span:
            continue
        x0, x1, x2 = f[i - 1], f[i], f[i + 1]
        y0, y1, y2 = v[i - 1], v[i], v[i + 1]
        denominator = (x0 - x1) * (x0 - x2) * (x1 - x2)
        hz = x1
        if abs(denominator) > 1e-12:
            a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denominator
            b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0)
                 + x0 * x0 * (y1 - y2)) / denominator
            if a < 0:
                hz = float(np.clip(-b / (2 * a), x0, x2))
        candidates.append((float(v[i]), -int(i), float(hz)))
    chosen = []
    for level, _, hz in sorted(candidates, reverse=True):
        if all(abs(hz - other) >= min_separation_hz for other, _ in chosen):
            chosen.append((hz, level))
            if len(chosen) >= limit:
                break
    return sorted(chosen)


def peak_label(hz):
    return f"{hz:.1f}" if hz < 100 else f"{hz:.0f}"


def place_peak_labels(apexes, bounds, obstacles=(), height=12):
    """Collision-free label boxes for ``(x, y, width, text, level)`` apexes.

    Strongest first: above the apex when there is headroom, otherwise beside
    it (right, then left, then one row lower). A label with no free place is dropped rather than
    drawn over another value. Returns ``(box, text, x, y, above)``.
    """
    bounds = pygame.Rect(bounds)
    taken = [pygame.Rect(box) for box in obstacles]
    placed = []
    for x, y, width, text, _ in sorted(apexes, key=lambda a: (-a[4], a[0])):
        side_top = max(bounds.y + 1, y - height // 2)
        options = [(pygame.Rect(x - width // 2, y - height - 3, width, height), True)]
        options += [(pygame.Rect(left, top, width, height), False)
                    for top in (side_top, side_top + height)
                    for left in (x + 4, x - 4 - width)]
        for box, above in options:
            if (bounds.contains(box)
                    and not any(box.inflate(4, 0).colliderect(other) for other in taken)):
                taken.append(box)
                placed.append((box, text, x, y, above))
                break
    return placed


def _draw_peak_labels(screen, rect, values, frequencies, xmin, xmax,
                      marker_hz=None, color=TEXT):
    """Frequency value above every prominent peak of a spectrum strip."""
    if rect.w < PEAK_LABEL_W or xmax <= xmin:
        return
    scale = (rect.w - 1) / (xmax - xmin)
    font = layout.font(10)
    obstacles, marker_x = [], None
    if marker_hz is not None and np.isfinite(marker_hz) and xmin <= marker_hz <= xmax:
        marker_x = rect.x + round((float(marker_hz) - xmin) * scale)
        obstacles.append(pygame.Rect(marker_x + 4, rect.y + 2, 70, 18))
    apexes = []
    for hz, level in spectrum_peaks(values, frequencies, limit=12):
        x = rect.x + round((hz - xmin) * scale)
        if not xmin <= hz <= xmax or (marker_x is not None and abs(x - marker_x) < 4):
            continue
        y = rect.bottom - 1 - round(min(1.0, max(0.0, level)) * (rect.h - 1))
        text = peak_label(hz)
        apexes.append((x, y, font.size(text)[0], text, level))
    for box, text, x, y, above in place_peak_labels(apexes, rect, obstacles,
                                                    font.get_height()):
        if above:
            pygame.draw.line(screen, color, (x, y - 1), (x, y - 3), 1)
        pygame.draw.rect(screen, NAVY, box)
        _text(screen, text, box, color, 10, "center")


def _translator(game, tr=None):
    return tr or getattr(game, "tr", None) or (lambda text: text)


def _tow_status(sonar, ship_speed=0.0):
    """Normalize the public TAS status for UI-only consumers and old fixtures."""
    status_fn = getattr(sonar, "tow_status", None)
    if status_fn is not None:
        status = dict(status_fn(ship_speed))
    else:
        state = getattr(getattr(sonar, "tow_state", "STOWED"), "value",
                        getattr(sonar, "tow_state", "STOWED"))
        payout = float(getattr(sonar, "tow_payout", 0.0))
        status = dict(state=state, payout=payout, payout_percent=payout * 100.0,
                      available=state == "STREAMED", handling_ok=True,
                      performance=float(getattr(sonar, "tow_performance", 0.0)),
                      depth_m=getattr(sonar, "towed_depth_m",
                                      config.SONAR_TOWED_DEPTH_M),
                      depth_target_m=getattr(sonar, "towed_depth_target_m",
                                             config.SONAR_TOWED_DEPTH_M))
    status.setdefault("payout_percent", float(status.get("payout", 0.0)) * 100.0)
    status.setdefault("performance", 0.0)
    status.setdefault("handling_ok", True)
    status.setdefault("available", False)
    return status


def _vds_status(sonar):
    """Public VDS status, or None for sonar fixtures without a VDS."""
    status_fn = getattr(sonar, "vds_status", None)
    return dict(status_fn()) if status_fn is not None else None


def active_echoes(sonar, now, window_s=ACTIVE_HISTORY_WINDOW_S):
    """Return bounded, recent measurement dictionaries without altering history."""
    limit = int(getattr(config, "SONAR_ECHO_HISTORY_MAX", 80))
    result = []
    for echo in list(getattr(sonar, "echo_history", []))[-limit:]:
        try:
            age = max(0.0, float(now) - float(echo["t"]))
            values = (float(echo["bearing"]), float(echo["range_nm"]),
                      float(echo.get("range_sigma_nm", 0.0)),
                      float(echo.get("snr_db", 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
        if age <= window_s and np.isfinite(values).all():
            item = dict(echo)
            item["age_s"] = age
            result.append(item)
    return result


def _echo_color(age_s):
    fade = max(0.0, 1.0 - age_s / ACTIVE_HISTORY_WINDOW_S)
    return tuple(round(NAVY[i] + fade * (CYAN[i] - NAVY[i])) for i in range(3))


def _active_geometry(panel, echoes):
    gap = 18
    left_w = round((panel.w - 48 - gap) * .57)
    ascope = pygame.Rect(panel.x + 46, panel.y + 83, left_w, panel.h - 130)
    polar = pygame.Rect(ascope.right + gap, ascope.y,
                        panel.right - ascope.right - gap - 18, ascope.h)
    max_range = max(5.0, max((float(e["range_nm"]) +
                              float(e.get("range_sigma_nm", 0.0))
                              for e in echoes), default=5.0))
    return ascope, polar, min(100.0, np.ceil(max_range / 5.0) * 5.0)


def _echo_point(polar, max_range, echo, distance=None):
    radius = max(10, min(polar.w, polar.h) // 2 - 13)
    bearing = np.deg2rad(float(echo["bearing"]))
    if distance is None:
        distance = min(max_range, float(echo["range_nm"]))
    radial = distance / max_range * radius
    return (round(polar.centerx + np.sin(bearing) * radial),
            round(polar.centery - np.cos(bearing) * radial))


def _ascope_point(ascope, max_range, echo):
    x = ascope.x + round(min(max_range, float(echo["range_nm"]))
                         / max_range * (ascope.w - 1))
    height = round(np.clip((float(echo.get("snr_db", 0)) + 12) / 28,
                           .08, 1.0) * (ascope.h - 12))
    return x, ascope.bottom - 2 - height


def _draw_active(game, panel, tr=None):
    """A-scope and bearing/range history made solely from echo_history."""
    screen, sonar = game.screen, game.sonar
    translate = _translator(game, tr)
    now = getattr(game, "sim_t", 0.0)
    echoes = active_echoes(sonar, now)
    latest = {}
    for echo in echoes:
        latest[echo.get("contact_id")] = echo

    _text(screen, translate("sonar.active_analysis"),
          (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    ready = bool(getattr(sonar, "ping_ready", True))
    remaining = float(getattr(sonar, "ping_cooldown_remaining",
                              getattr(sonar, "ping_cooldown", 0.0)))
    readiness = translate("ui.ready") if ready else f"{remaining:.0f}s"
    _text(screen, message("sonar.line.ping_history", ping=translate('PING'),
                          readiness=readiness, count=len(echoes),
                          window=translate('sonar.echo_window')),
          (panel.x + 16, panel.y + 36, panel.w - 32, 20),
          CYAN if ready else AMBER, 13)

    ascope, polar, max_range = _active_geometry(panel, echoes)
    pygame.draw.rect(screen, NAVY, ascope)
    pygame.draw.rect(screen, NAVY, polar)

    for i in range(5):
        x = ascope.x + round(i * (ascope.w - 1) / 4)
        pygame.draw.line(screen, GRID, (x, ascope.y), (x, ascope.bottom - 1))
        _text(screen, f"{max_range * i / 4:.0f}",
              (x - 24, ascope.bottom + 4, 48, 19), DIM, 12, "center")
    pygame.draw.rect(screen, GRID, ascope, 1)
    _text(screen, translate("sonar.ascope"),
          (ascope.x, ascope.y - 22, ascope.w, 19), DIM, 13)
    _text(screen, translate("sonar.range_axis"),
          (ascope.right - 145, ascope.bottom + 24, 145, 19), DIM, 12, "right")

    for echo in latest.values():
        sigma = max(0.0, float(echo.get("range_sigma_nm", 0.0)))
        x, y = _ascope_point(ascope, max_range, echo)
        half = round(sigma / max_range * (ascope.w - 1))
        color = _echo_color(float(echo["age_s"]))
        pygame.draw.line(screen, color, (x, ascope.bottom - 2),
                         (x, y), 2)
        pygame.draw.line(screen, AMBER, (x - half, ascope.bottom - 7),
                         (x + half, ascope.bottom - 7), 2)
        pygame.draw.circle(screen, color, (x, y), 4)

    center = polar.center
    radius = max(10, min(polar.w, polar.h) // 2 - 13)
    for fraction in (.25, .5, .75, 1.0):
        pygame.draw.circle(screen, GRID, center, round(radius * fraction), 1)
    pygame.draw.line(screen, GRID, (center[0], center[1] - radius),
                     (center[0], center[1] + radius))
    pygame.draw.line(screen, GRID, (center[0] - radius, center[1]),
                     (center[0] + radius, center[1]))
    _text(screen, translate("sonar.polar_heading"),
          (polar.x, polar.y - 22, polar.w, 19), DIM, 13, "center")
    _text(screen, "N", (center[0] - 10, center[1] - radius, 20, 18), DIM, 12, "center")
    with layout.clip_to(screen, polar):
        for echo in echoes:
            distance = min(max_range, float(echo["range_nm"]))
            sigma = max(0.0, float(echo.get("range_sigma_nm", 0.0)))
            color = _echo_color(float(echo["age_s"]))

            def point(value):
                return _echo_point(polar, max_range, echo, value)

            pygame.draw.line(screen, AMBER, point(max(0.0, distance - sigma)),
                             point(min(max_range, distance + sigma)), 2)
            pygame.draw.circle(screen, color, point(distance), 3)
    if not echoes:
        _text(screen, translate("sonar.no_stored_echoes"),
              (panel.x + 60, panel.centery - 10, panel.w - 120, 22),
              AMBER, 14, "center")


def _draw_waterfall(game, panel, page):
    screen, sonar = game.screen, game.sonar
    title = "sonar.omni_broadband" if page == 0 else "sonar.beam_narrowband"
    _text(screen, title, (panel.x + 16, panel.y + 10, panel.w - 32, 23), CYAN, 16)
    _draw_display_status(game, panel)
    plot = _waterfall_plot(panel, page)
    if plot.w < 2 or plot.h < 2:
        return
    processed = _waterfall(game, page, plot)
    _grid(screen, plot, 360 if page == 0 else 300,
          "sonar.bearing_axis_short" if page == 0 else "sonar.hz_linear")
    _text(screen, "sonar.new", (panel.x + 8, plot.y, 45, 18), CYAN, 12)
    _text(screen, "sonar.old", (panel.x + 8, plot.bottom - 18, 45, 18), DIM, 12)
    _, times, _ = _history_for_page(sonar, page)
    timing = (message("sonar.line.history_timed", newest=f"{times[-1]:.1f}",
                      oldest=f"{times[0]:.1f}", rows=len(processed)) if len(times) else
              message("sonar.line.history_untimed", rows=len(processed)))
    _text(screen, timing, (panel.x + 16, panel.y + 35,
                           panel.w - 32 - (196 if page == 1 else 0), 20), DIM, 12)
    if not len(processed):
        _text(screen, "sonar.no_receiver_data", (plot.x, plot.centery - 10, plot.w, 22),
              DIM, 16, "center")
    if page == 0:
        profile = pygame.Rect(plot.x, panel.y + 56, plot.w, 42)
        pygame.draw.rect(screen, NAVY, profile)
        current = getattr(getattr(sonar, "receiver", None), "broadband", [])
        if len(current):
            _trace(screen, profile, _circular_broadband(current, profile.w))
        _text(screen, "sonar.instantaneous",
              (profile.x + 5, profile.y + 2, 150, 18), DIM, 12)
        bearing = getattr(sonar, "listen_bearing", 0.0) % 360
        half = getattr(sonar, "beam_width_deg", 12.0) / 2
        with layout.clip_to(screen, plot):
            for value in ((bearing - half) % 360, (bearing + half) % 360):
                x = plot.x + round(value / 360 * (plot.w - 1))
                pygame.draw.line(screen, DIM, (x, plot.y), (x, plot.bottom - 1))
            x = plot.x + round(bearing / 360 * (plot.w - 1))
            pygame.draw.line(screen, AMBER, (x, plot.y), (x, plot.bottom - 1))
            own_lobe = getattr(getattr(sonar, "receiver", None),
                               "own_noise_lobe", None)
            if own_lobe:
                center = float(own_lobe["bearing"]) % 360.0
                lobe_half = float(own_lobe["width_deg"]) / 2.0
                for value in ((center - lobe_half) % 360,
                              (center + lobe_half) % 360):
                    lx = plot.x + round(value / 360 * (plot.w - 1))
                    pygame.draw.line(screen, (139, 91, 71),
                                     (lx, plot.y), (lx, plot.bottom - 1), 1)
            # The hull array's baffles astern: dotted edges.
            observer = _sonar_observer(game)
            course = getattr(observer, "course", None)
            if course is not None:
                astern = (float(course) + 180.0) % 360.0
                for edge in (-config.SONAR_BAFFLE_HALF_DEG, config.SONAR_BAFFLE_HALF_DEG):
                    bx = plot.x + round(((astern + edge) % 360.0) / 360 * (plot.w - 1))
                    for y in range(plot.y, plot.bottom, 6):
                        pygame.draw.line(screen, DIM, (bx, y), (bx, min(plot.bottom - 1, y + 2)))
    else:
        spectrum_rect = pygame.Rect(plot.x, panel.y + 56, plot.w, 42)
        pygame.draw.rect(screen, NAVY, spectrum_rect)
        receiver = getattr(sonar, "receiver", None)
        tools = getattr(game, "sonar_tools", None)
        seconds = getattr(tools, "integration_s", 2)
        columns = list(getattr(sonar, "integration_columns", ()))
        current = (analysis_tools.integrate([column[0] for column in columns], seconds)
                   if columns else np.asarray(getattr(receiver, "spectrum", []), dtype=float))
        process = getattr(sonar, "process_lofar_column", None)
        assist = bool(getattr(game, "operator_assist", lambda: True)())
        vernier = bool(getattr(tools, "vernier", False))
        xmin, xmax = 0.0, config.LOFAR_FMAX_HZ
        if vernier and columns:
            xmin, xmax = analysis_tools.vernier_window(tools.lofar_cursor_hz)
            native = analysis_tools.integrate([column[1] for column in columns], seconds)
            native_hz = np.arange(native.size) * 0.5
            inside = (native_hz >= xmin) & (native_hz <= xmax)
            gain = 10.0 ** (getattr(sonar, "gain_db", 0.0) / 20.0)
            latest = np.clip(native[inside] * gain, 0.0, 1.0)
            labelled = (latest, native_hz[inside])
        elif len(current):
            bins = process(list(current), _sonar_observer(game)) if process else current
            latest = _linear_lofar(bins, plot.w)
            labelled = (np.asarray(bins), _lofar_frequencies(len(bins)))
        else:
            latest = processed[-1] if len(processed) else []
            labelled = (latest, np.linspace(0.0, config.LOFAR_FMAX_HZ, len(latest)))
        _trace(screen, spectrum_rect, latest)

        def strip_x(frequency):
            return spectrum_rect.x + round((frequency - xmin) / max(1e-9, xmax - xmin)
                                           * (spectrum_rect.w - 1))

        if not vernier:
            for frequency, label in ((40.0, "0-40"), (100.0, "40-100"),
                                     (300.0, "100-300")):
                x = strip_x(frequency)
                pygame.draw.line(screen, GRID, (x, spectrum_rect.y),
                                 (x, plot.bottom - 1), 1)
                start = 0.0 if label == "0-40" else 40.0 if label == "40-100" else 100.0
                left = strip_x(start)
                _text(screen, label + " Hz", (left + 4, spectrum_rect.bottom - 17,
                      max(40, x - left - 8), 16), DIM, 10)
        else:
            _text(screen, message("sonar.vernier_axis", low=f"{xmin:.1f}", high=f"{xmax:.1f}"),
                  (spectrum_rect.x + 4, spectrum_rect.bottom - 17, 220, 16), DIM, 10)
        low = float(getattr(sonar, "band_low_hz", 0.0))
        high = float(getattr(sonar, "band_high_hz", config.LOFAR_FMAX_HZ))
        for frequency in (low, high):
            if xmin <= frequency <= xmax:
                x = strip_x(frequency)
                pygame.draw.line(screen, AMBER, (x, spectrum_rect.y),
                                 (x, spectrum_rect.bottom - 1 if vernier else plot.bottom - 1), 1)
        held = getattr(sonar, "peak_hold", False)
        if held and not vernier:
            peak = getattr(sonar, "peak_spectrum", getattr(receiver, "peak_spectrum", []))
            if peak is not None and len(peak):
                peak = process(peak, _sonar_observer(game)) if process else peak
                labelled = (peak, _lofar_frequencies(len(peak)))
                peak = _linear_lofar(peak, plot.w)
            else:
                peak = np.max(processed, axis=0) if len(processed) else []
                labelled = (peak, np.linspace(0.0, config.LOFAR_FMAX_HZ, len(peak)))
            _trace(screen, spectrum_rect, peak, AMBER)
        if assist:
            # Training aid only: the operator finds lines with the cursor.
            _draw_peak_labels(screen, spectrum_rect, *labelled, xmin, xmax)
        # Above the strip, so it never hides the peak values of 0-40 Hz.
        legend = pygame.Rect(panel.right - 196, panel.y + 35, 180, 20)
        _text(screen, message("sonar.live_peak", state=message(
                  "sonar.peak_held" if held else "sonar.peak_off")),
              legend, AMBER if held else DIM, 12, "right")
        bearings = getattr(sonar, "lofar_bearings", [])
        note = (message("sonar.line.row_bearings", newest=f"{bearings[-1] % 360:05.1f}",
                        oldest=f"{bearings[0] % 360:05.1f}")
                if len(bearings) else message("sonar.line.history_bearing"))
        _text(screen, note, (plot.x, plot.bottom + 24, plot.w - 160, 18), DIM, 12)

        base = _selected_harmonic(game)
        top = spectrum_rect.y
        with layout.clip_to(screen, pygame.Rect(spectrum_rect.x, top, spectrum_rect.w,
                                                plot.bottom - top)):
            if base is not None:
                for multiple, frequency in analysis_tools.harmonic_comb(base, xmax):
                    if frequency < xmin:
                        continue
                    x = strip_x(frequency)
                    pygame.draw.line(screen, AMBER, (x, top),
                                     (x, spectrum_rect.bottom - 1 if vernier else plot.bottom - 1), 1)
                    _text(screen, f"{multiple if multiple > 1 else ''}f",
                          (x + 3, top + 2, 24, 16), AMBER, 11)
            notch = getattr(sonar, "operator_notch_hz", None)
            if notch is not None and xmin <= notch <= xmax:
                x = strip_x(notch)
                pygame.draw.line(screen, DIM, (x, top), (x, spectrum_rect.bottom - 1), 3)
            if tools is not None and xmin <= tools.lofar_cursor_hz <= xmax:
                x = strip_x(tools.lofar_cursor_hz)
                pygame.draw.line(screen, TEXT, (x, top),
                                 (x, spectrum_rect.bottom - 1 if vernier else plot.bottom - 1), 1)


def _harmonic_candidates(sonar):
    """Expose bounded receiver peaks as operator-selectable hypotheses."""
    peaks = getattr(getattr(sonar, "receiver", None), "peaks", [])
    return sorted({float(hz) for hz, _ in list(peaks)[:6]
                   if np.isfinite(hz) and 0 < float(hz) <= config.LOFAR_FMAX_HZ})


def _selected_harmonic(game):
    """The operator's fundamental (placed with the cursor), if any."""
    selected = getattr(game, "sonar_harmonic_hz", None)
    if selected is None or not np.isfinite(selected) or selected <= 0:
        return None
    return float(selected)


def _library_rows(game):
    """Class library: catalog classes sorted by fit to the operator's marks."""
    library = getattr(game, "sonar_class_library", None)
    if library is None:
        return [("sonar.catalog_manual_hint", TEXT, 13)]
    marks = game.sonar_library_marks()
    ranked = library(3)
    if not ranked:
        return [("sonar.catalog_manual_hint", TEXT, 13)]
    key = ("sonar.library.header" if marks >= class_library.SURE_MARKS
           else "sonar.library.header_hint")
    rows = [(message(key, marks=marks), AMBER, 13)]
    for index, (signature, fit) in enumerate(ranked, 1):
        rows.append((message("sonar.library.row", index=index, fit=f"{fit:.0%}",
                             name=str(getattr(signature, "label", signature.key))),
                     TEXT, 13))
    return rows


def _demon_evidence(sonar):
    spectrum = np.asarray(getattr(getattr(sonar, "receiver", None), "demon_spectrum", []))
    analysis = getattr(sonar, "demon_analysis", None) or {}
    rate = analysis.get("blade_rate_hz")
    # Require a real envelope line above the floor before presenting hypotheses.
    evidence = (spectrum.size >= 3 and np.isfinite(spectrum).all()
                and float(np.max(spectrum)) > max(.02, float(np.median(spectrum)) * 2)
                and analysis.get("confidence", 0) >= .2
                and rate is not None and rate > 0)
    return spectrum, analysis, bool(evidence)


def _draw_demon(game, panel):
    screen = game.screen
    sonar = game.sonar
    spectrum, analysis, evidence = _demon_evidence(sonar)
    _text(screen, "sonar.demon_title", (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    _draw_display_status(game, panel)
    _text(screen, "sonar.demon_caption",
          (panel.x + 16, panel.y + 37, panel.w - 32, 20), DIM, 13)
    full = pygame.Rect(panel.x + 57, panel.y + 62, panel.w - 83,
                       panel.h - 109)
    spectrum_rect = pygame.Rect(full.x, full.y, full.w, 44)
    plot = pygame.Rect(full.x, spectrum_rect.bottom + 8, full.w,
                       full.bottom - spectrum_rect.bottom - 8)
    pygame.draw.rect(screen, NAVY, spectrum_rect)
    pygame.draw.rect(screen, NAVY, plot)
    tools = getattr(game, "sonar_tools", None)
    assist = bool(getattr(game, "operator_assist", lambda: True)())
    seconds = getattr(tools, "integration_s", 2)
    columns = list(getattr(sonar, "integration_columns", ()))
    if columns:
        spectrum = analysis_tools.integrate([column[2] for column in columns], seconds)
    visible_spectrum = spectrum[:int(DEMON_DISPLAY_MAX_HZ)]
    if visible_spectrum.size:
        _trace(screen, spectrum_rect, np.concatenate(([0.0], visible_spectrum)))
        if assist:
            modulation = analysis.get("modulation_peak_hz")
            _draw_peak_labels(screen, spectrum_rect, visible_spectrum,
                              np.arange(1, visible_spectrum.size + 1, dtype=float),
                              0.0, DEMON_DISPLAY_MAX_HZ,
                              None if modulation is None else float(modulation))
    black, contrast, palette, history_fraction = _display_controls(game)
    history_rows = max(1, round(config.SONAR_DEMON_HISTORY_ROWS * history_fraction))
    rows = [np.asarray(row)[:int(DEMON_DISPLAY_MAX_HZ)]
            for row in list(getattr(sonar, "demon_history", ()))[-history_rows:]]
    if rows and seconds > analysis_tools.NATIVE_INTEGRATION_S:
        rows = list(analysis_tools.integrate_rows(rows, seconds))
    bitmap = rows
    if rows and len(rows) < history_rows:
        bitmap = [[0.0] * len(rows[0]) for _ in range(history_rows - len(rows))] + rows
    key = (id(sonar), "demon", plot.size,
           getattr(getattr(sonar, "receiver", None), "sequence", None), len(rows),
           black, contrast, palette, history_fraction, seconds)
    cached = _WATERFALL_CACHE.get(key)
    if cached is None:
        cached = (waterfall_surface(bitmap, *plot.size, black_level=black,
                                    contrast=contrast, palette=palette), rows)
        _WATERFALL_CACHE[key] = cached
        while len(_WATERFALL_CACHE) > 4:
            _WATERFALL_CACHE.popitem(last=False)
    _WATERFALL_CACHE.move_to_end(key)
    screen.blit(cached[0], plot)
    _grid(screen, plot, DEMON_DISPLAY_MAX_HZ, localize("sonar.demon_axis"))
    _text(screen, "sonar.new", (panel.x + 8, plot.y, 45, 18), CYAN, 12)
    _text(screen, "sonar.old", (panel.x + 8, plot.bottom - 18, 45, 18), DIM, 12)
    peak = analysis.get("modulation_peak_hz")
    if (assist and peak is not None and np.isfinite(peak)
            and 0.0 <= float(peak) <= DEMON_DISPLAY_MAX_HZ):
        x = plot.x + round(float(peak) / DEMON_DISPLAY_MAX_HZ * (plot.w - 1))
        pygame.draw.line(screen, AMBER, (x, spectrum_rect.y),
                         (x, plot.bottom - 1), 1)
        _text(screen, f"{float(peak):.1f} Hz",
              (x + 4, spectrum_rect.y + 2, 70, 18), AMBER, 11)
    if tools is not None:
        # Operator marks: S = shaft line, B = blade line, white = cursor.
        for mark, label, color in ((tools.shaft_hz, "S", CYAN),
                                   (tools.blade_hz, "B", AMBER),
                                   (tools.demon_cursor_hz, "", TEXT)):
            if mark is None or not 0.0 <= mark <= DEMON_DISPLAY_MAX_HZ:
                continue
            x = plot.x + round(float(mark) / DEMON_DISPLAY_MAX_HZ * (plot.w - 1))
            pygame.draw.line(screen, color, (x, spectrum_rect.y), (x, plot.bottom - 1), 1)
            if label:
                _text(screen, f"{label} {mark:.1f}", (x + 3, spectrum_rect.y + 2, 60, 16),
                      color, 11)
    if assist and not evidence:
        _text(screen, "sonar.low_evidence",
              (plot.x + 12, plot.y + 12, plot.w - 24, 22), AMBER, 14)


def _bearing_series(points):
    """Unwrap adjacent observed bearings so 359 -> 1 crosses north, not 180."""
    times = np.asarray([p.t for p in points], dtype=float)
    bearings = np.rad2deg(np.unwrap(np.deg2rad([p.bearing for p in points])))
    return times, bearings


def _tma_plot(panel, points):
    plot = pygame.Rect(panel.x + 65, panel.y + 69, panel.w - 95, panel.h - 116)
    times, bearings = _bearing_series(points)
    lo = float(np.min(bearings)) - 3 if len(points) else 0.0
    hi = float(np.max(bearings)) + 3 if len(points) else 360.0
    start = float(times[0]) if len(points) else 0.0
    end = max(start + 1, float(times[-1])) if len(points) else 60.0
    xy = [(plot.x + round((t - start) / (end - start) * (plot.w - 1)),
           plot.bottom - 1 - round((b - lo) / (hi - lo) * (plot.h - 1)))
          for t, b in zip(times, bearings)]
    return plot, times, bearings, xy


def tma_observation_summary(track, now, solution_quality=0.0):
    """Summarize only the bearing history and recorded ownship legs."""
    points = list(getattr(track, "pts", []))
    if not points:
        return dict(rate=None, legs=0, geometry="KEINE",
                    state="ZU WENIG HISTORIE", age=None, span=0.0)
    times, bearings = _bearing_series(points)
    span = float(times[-1] - times[0]) if len(points) > 1 else 0.0
    rate = None
    if span > 0.0:
        weights = np.asarray([
            1.0 / max(0.05, float(getattr(point, "uncertainty_deg", 1.0))) ** 2
            for point in points], dtype=float)
        mean_time = float(np.average(times, weights=weights))
        mean_bearing = float(np.average(bearings, weights=weights))
        centered = times - mean_time
        denom = float(np.dot(weights, centered * centered))
        if denom > 0.0:
            rate = float(np.dot(weights * centered,
                                bearings - mean_bearing) / denom * 60.0)

    leg_courses = []
    for point in points:
        course = getattr(point, "fcourse", None)
        if course is None:
            continue
        if (not leg_courses or abs(config.angle_diff_deg(course, leg_courses[-1]))
                >= config.TMA_MIN_COURSE_CHG_DEG):
            leg_courses.append(course)
    legs = len(leg_courses)
    course_span = max((abs(config.angle_diff_deg(first, second))
                       for i, first in enumerate(leg_courses)
                       for second in leg_courses[i + 1:]), default=0.0)
    geometry_ok = legs >= 2 and course_span >= config.TMA_MIN_COURSE_CHG_DEG
    age = max(0.0, float(now) - float(times[-1]))
    enough_history = (len(points) >= config.TMA_MIN_PTS
                      and span >= config.TMA_MIN_SPAN_S)
    if age > 30.0:
        state = "VERALTET"
    elif not enough_history:
        state = "ZU WENIG HISTORIE"
    elif not geometry_ok:
        state = "SCHWACHE GEOMETRIE"
    elif solution_quality < config.TMA_RANGE_MIN_QUALITY:
        state = "KONVERGIEREND"
    else:
        state = "LOESUNG STABIL"
    return dict(rate=rate, legs=legs,
                geometry="BRAUCHBAR" if geometry_ok else "SCHWACH",
                state=state, age=age, span=span)


def tma_closing_rate_kn(ship, bearing_deg, course_deg, speed_kn):
    """Range-rate (closing positive) along the line of sight to a TMA fix.

    Pure display-derived value from data already shown alongside it (TMA
    course/speed, own ship state); never stored, so it carries no save-schema
    or determinism risk. This is what a real Doppler shift on an active ping
    would report - the sign and magnitude of the closing rate - without
    modeling the acoustic frequency shift itself.
    """
    if course_deg is None or speed_kn is None:
        return None
    bearing = math.radians(bearing_deg)
    los = (math.sin(bearing), -math.cos(bearing))
    course = math.radians(course_deg)
    target_vx, target_vy = speed_kn * math.sin(course), -speed_kn * math.cos(course)
    own_course = math.radians(getattr(ship, "course", 0.0))
    own_speed = float(getattr(ship, "speed", 0.0))
    own_vx, own_vy = own_speed * math.sin(own_course), -own_speed * math.cos(own_course)
    relative_vx, relative_vy = target_vx - own_vx, target_vy - own_vy
    return -(relative_vx * los[0] + relative_vy * los[1])


def _draw_tma(game, panel):
    screen = game.screen
    contact = getattr(game, "selected_contact", None)
    track = getattr(game.sonar, "_tracks", {}).get(getattr(contact, "target_id", None))
    points = getattr(track, "pts", [])
    _text(screen, "sonar.tma_title", (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    plot, times, bearings, xy = _tma_plot(panel, points)
    pygame.draw.rect(screen, NAVY, plot)
    summary = tma_observation_summary(
        track, getattr(game, "sim_t", 0.0),
        getattr(contact, "tma_quality", 0.0) if contact is not None else 0.0)
    lo = float(np.min(bearings)) - 3 if len(points) else 0.0
    hi = float(np.max(bearings)) + 3 if len(points) else 360.0
    start = float(times[0]) if len(points) else 0.0
    end = max(start + 1, float(times[-1])) if len(points) else 60.0
    for i in range(5):
        x = plot.x + round(i * (plot.w - 1) / 4)
        y = plot.bottom - 1 - round(i * (plot.h - 1) / 4)
        pygame.draw.line(screen, GRID, (x, plot.y), (x, plot.bottom - 1))
        pygame.draw.line(screen, GRID, (plot.x, y), (plot.right - 1, y))
        _text(screen, f"{start + (end - start) * i / 4:.0f}",
              (x - 30, plot.bottom + 5, 60, 18), DIM, 12, "center")
        _text(screen, f"{(lo + (hi - lo) * i / 4) % 360:05.1f}",
              (panel.x + 5, y - 8, 55, 18), DIM, 12, "right")
    _text(screen, "sonar.sim_time_axis", (plot.right - 140, plot.bottom + 24, 140, 18), DIM, 12, "right")
    method = getattr(game, "tma_method", "hypothesis")
    _text(screen, message("sonar.tma_method_line",
                          method=display_message("tma_method", method)),
          (panel.x + 16, panel.y + 37, panel.w - 32, 20), AMBER, 12)
    if len(points):
        with layout.clip_to(screen, plot):
            if len(xy) > 1:
                pygame.draw.lines(screen, CYAN, False, xy, 2)
            for point in xy:
                pygame.draw.circle(screen, TEXT, point, 3)
            if method == "dotstack":
                _draw_tma_dot_stack(game, contact, points, plot, times, start, end)
            else:
                _draw_tma_hypothesis(game, contact, points, plot, times, bearings, lo, hi,
                                     start, end)
        if method == "ekelund" and contact is not None and hasattr(game, "tma_ekelund"):
            estimate = game.tma_ekelund(contact)
            _text(screen, (message("sonar.ekelund_line", range=f"{estimate[0]:.1f}",
                                   error=f"{estimate[1]:.1f}") if estimate is not None
                           else "sonar.ekelund_pending"),
                  (plot.x + 8, plot.y + 30, plot.w - 16, 20), AMBER, 13)
        _text(screen, message("sonar.line.observations", count=len(points),
                              duration=f"{times[-1] - times[0]:.1f}"),
               (plot.x, plot.bottom + 24, plot.w - 145, 18), DIM, 12)
        rate = (f"{summary['rate']:+.2f} deg/min"
                if summary["rate"] is not None else "-- deg/min")
        _text(screen, message(
                      "sonar.tma_summary", rate=rate, legs=summary["legs"],
                      geometry=display_message("tma", summary["geometry"]),
                      state=display_message("tma", summary["state"])),
              (plot.x + 8, plot.y + 8, plot.w - 16, 20),
              AMBER if summary["state"] != "LOESUNG STABIL" else CYAN, 13)
    else:
        _text(screen, "sonar.no_bearing_series",
              (plot.x, plot.centery, plot.w, 22), DIM, 14, "center")


def _draw_tma_hypothesis(game, contact, points, plot, times, bearings, lo, hi,
                         start, end):
    """Predicted bearings of the operator hypothesis (amber) and, as a
    training aid, of the automatic proposal (dim); residuals along the foot."""
    if contact is None or not hasattr(game, "tma_hypothesis"):
        return
    screen = game.screen
    unwrapped = np.asarray(bearings, dtype=float)

    def curve(hypothesis):
        predicted = []
        for index, residual in enumerate(tma_operator.residuals(points, hypothesis)):
            value = unwrapped[index] - residual
            x = plot.x + round((float(times[index]) - start) / max(1e-9, end - start)
                               * (plot.w - 1))
            y = plot.bottom - 1 - round((value - lo) / max(1e-9, hi - lo) * (plot.h - 1))
            predicted.append((x, y))
        return predicted

    if getattr(game, "operator_assist", lambda: False)():
        proposal = getattr(game.sonar, "tma_proposals", {}).get(contact.target_id)
        if proposal is not None:
            ref = points[-1]
            ghost = tma_operator.Hypothesis(
                proposal.course, proposal.speed,
                max(tma_operator.RANGE_MIN_NM,
                    float(np.hypot(proposal.pos[0] - ref.fx, proposal.pos[1] - ref.fy))))
            line = curve(ghost)
            if len(line) > 1:
                pygame.draw.lines(screen, DIM, False, line, 1)
    hypothesis = game.tma_hypothesis(contact)
    line = curve(hypothesis)
    if len(line) > 1:
        pygame.draw.lines(screen, AMBER, False, line, 2)
    # Residual strip: +/-10 deg around the foot line of the plot.
    strip = pygame.Rect(plot.x, plot.bottom - 40, plot.w, 36)
    pygame.draw.line(screen, GRID, (strip.x, strip.centery), (strip.right - 1, strip.centery))
    for index, residual in enumerate(tma_operator.residuals(points, hypothesis)):
        x = plot.x + round((float(times[index]) - start) / max(1e-9, end - start)
                           * (plot.w - 1))
        y = strip.centery - round(max(-10.0, min(10.0, residual)) / 10.0 * (strip.h / 2 - 2))
        pygame.draw.circle(screen, AMBER, (x, y), 2)


def _draw_tma_dot_stack(game, contact, points, plot, times, start, end):
    """Residual rows at three range multiples of the hypothesis: the flat
    row shows the range the bearings support (classic dot stack)."""
    if contact is None or not hasattr(game, "tma_hypothesis"):
        return
    screen = game.screen
    rows = tma_operator.dot_stack(points, game.tma_hypothesis(contact))
    row_h = max(24, (plot.h - 60) // max(1, len(rows)))
    for index, (range_nm, residuals) in enumerate(rows):
        strip = pygame.Rect(plot.x, plot.bottom - (len(rows) - index) * row_h - 4,
                            plot.w, row_h - 4)
        pygame.draw.line(screen, GRID, (strip.x, strip.centery),
                         (strip.right - 1, strip.centery))
        _text(screen, f"{range_nm:.1f} NM", (strip.x + 4, strip.y, 90, 16), DIM, 11)
        for point_index, residual in enumerate(residuals):
            x = plot.x + round((float(times[point_index]) - start) / max(1e-9, end - start)
                               * (plot.w - 1))
            y = strip.centery - round(max(-10.0, min(10.0, residual)) / 10.0
                                      * (strip.h / 2 - 2))
            pygame.draw.circle(screen, AMBER if index == 1 else TEXT, (x, y), 2)


def _draw_environment(game, panel):
    """Draw only the operator-measured profile and observed array reports."""
    screen, sonar = game.screen, game.sonar
    _text(screen, "sonar.sound_profile",
          (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    _text(screen, "sonar.bt_caption",
          (panel.x + 16, panel.y + 37, panel.w - 32, 20), DIM, 13)
    profile = getattr(sonar, "bt_profile", None)
    plot = pygame.Rect(panel.x + 66, panel.y + 72,
                       panel.w - 96, max(150, panel.h - 220))
    pygame.draw.rect(screen, NAVY, plot)
    pygame.draw.rect(screen, GRID, plot, 1)
    if profile and profile.get("depths_m") and profile.get("speeds_m_s"):
        depths = np.asarray(profile["depths_m"], dtype=float)
        speeds = np.asarray(profile["speeds_m_s"], dtype=float)
        max_depth = max(1.0, float(np.max(depths)))
        lo, hi = float(np.min(speeds)) - .5, float(np.max(speeds)) + .5
        for i in range(5):
            y = plot.y + round(i * (plot.h - 1) / 4)
            pygame.draw.line(screen, GRID, (plot.x, y), (plot.right - 1, y))
            _text(screen, f"{max_depth * i / 4:.0f}m",
                  (panel.x + 5, y - 8, 56, 18), DIM, 12, "right")
        points = [(plot.x + round((speed - lo) / max(.01, hi - lo) * (plot.w - 1)),
                   plot.y + round(depth / max_depth * (plot.h - 1)))
                  for speed, depth in zip(speeds, depths)]
        if len(points) > 1:
            pygame.draw.lines(screen, CYAN, False, points, 2)
        thermo = float(profile["thermocline_m"])
        ty = plot.y + round(thermo / max_depth * (plot.h - 1))
        pygame.draw.line(screen, AMBER, (plot.x, ty), (plot.right - 1, ty), 2)
        _text(screen, message("sonar.line.thermocline", depth=f"{thermo:.0f}"),
              (plot.x + 8, ty - 20, 210, 18), AMBER, 12)
        _text(screen, message("sonar.line.sound_speed", low=f"{lo:.1f}", high=f"{hi:.1f}"),
              (plot.x, plot.bottom + 5, plot.w, 18), DIM, 12)
        mouse = profile_cursor.pointer(game)
        if mouse is not None and plot.collidepoint(mouse):
            depth = (mouse[1] - plot.y) / max(1, plot.h - 1) * max_depth
            speed = profile_cursor.speed_at(depths, speeds, depth)
            key = ("sonar.cursor.depth_above" if depth < thermo
                   else "sonar.cursor.depth_below")
            profile_cursor.draw_crosshair(screen, plot, y=mouse[1])
            profile_cursor.draw_label(screen, message(key, depth=f"{depth:.0f}",
                                                      speed=f"{speed:.1f}"),
                                      mouse, plot)
    else:
        _text(screen, "sonar.no_profile",
              (plot.x, plot.centery - 20, plot.w, 22), AMBER, 16, "center")
        _text(screen, "sonar.deploy_bt",
              (plot.x, plot.centery + 8, plot.w, 20), DIM, 14, "center")

    max_depth = (float(max(profile.get("depths_m", [300]))) if profile else 300.0)
    tow = _tow_status(sonar, getattr(_sonar_observer(game), "speed", 0.0))
    actual = float(tow.get("depth_m", config.SONAR_TOWED_DEPTH_M))
    target = float(tow.get("depth_target_m", actual))
    ay = plot.y + round(min(actual, max_depth) / max_depth * (plot.h - 1))
    pygame.draw.line(screen, (120, 210, 170), (plot.x, ay), (plot.right - 1, ay), 1)
    _text(screen, message("sonar.line.tow", state=display_message('tow', tow['state']),
                          payout=f"{tow['payout_percent']:.0f}", actual=f"{actual:.0f}",
                          target=f"{target:.0f}"),
          (plot.right - 248, ay - 19, 240, 18), (120, 210, 170), 12, "right")
    vds = _vds_status(sonar)
    if vds is not None and vds["state"] != "STOWED":
        vds_actual = float(vds["depth_m"])
        vy = plot.y + round(min(vds_actual, max_depth) / max_depth * (plot.h - 1))
        pygame.draw.line(screen, (210, 170, 120), (plot.x, vy), (plot.right - 1, vy), 1)
        _text(screen, message("sonar.line.vds", state=display_message('tow', vds['state']),
                              payout=f"{vds['payout_percent']:.0f}", actual=f"{vds_actual:.0f}",
                              target=f"{float(vds['depth_target_m']):.0f}"),
              (plot.x + 8, vy - 19, 240, 18), (210, 170, 120), 12)

    y = plot.bottom + 29
    _text(screen, "sonar.array_comparison", (panel.x + 16, y, panel.w - 32, 20), CYAN, 14)
    y += 23
    contacts = sorted(sonar.active_contacts(), key=lambda contact: contact.id)
    for contact in contacts[:4]:
        reports = getattr(contact, "array_observations", {})
        bow, towed, vds_report = reports.get("BOW"), reports.get("TOWED"), reports.get("VDS")
        report_text = lambda report: (f"{report['bearing']:05.1f} / {report['snr']:+.1f}dB"
                                      if report else "  --.- / --")
        bow_text, towed_text = report_text(bow), report_text(towed)
        status_raw = getattr(contact, "fusion_status", "KEINE DATEN")
        status = display_value("fusion", status_raw)
        color = (config.COLOR_OK if status_raw == "BESTAETIGT" else
                 config.COLOR_WARN if "DIVERGENT" in status_raw else DIM)
        _text(screen, message("sonar.line.array_contact",
                              contact=observations.contact_display_id(game, contact),
                              bow=bow_text, towed=towed_text,
                              vds=report_text(vds_report), status=status),
              (panel.x + 20, y, panel.w - 40, 19), color, 12)
        y += 20
    if not contacts:
        _text(screen, "sonar.no_array_contacts",
              (panel.x + 20, y, panel.w - 40, 19), DIM, 13)


def _detail_evidence(game, page):
    """Return page-specific public evidence provenance, age, and freshness."""
    sonar = game.sonar
    now = float(getattr(game, "sim_t", 0.0))
    stamp = None
    if page in (0, 1, 2):
        source = localize("sonar.source.receiver")
        times = getattr(sonar, "history_times" if page == 0 else "lofar_times", [])
        if len(times):
            stamp = float(times[-1])
    elif page == 3:
        source = localize("sonar.source.tma_track")
        contact = getattr(game, "selected_contact", None)
        track = getattr(sonar, "_tracks", {}).get(getattr(contact, "target_id", None))
        points = getattr(track, "pts", [])
        stamps = ([float(points[-1].t)] if points else [])
        tma_seen = getattr(contact, "tma_seen", None)
        if tma_seen is not None:
            stamps.append(float(tma_seen))
        if stamps:
            stamp = max(stamps)
    elif page == 4:
        source = localize("sonar.source.bt_profile")
        profile = getattr(sonar, "bt_profile", None)
        if profile is not None and profile.get("t") is not None:
            stamp = float(profile["t"])
    else:
        echoes = active_echoes(sonar, now)
        if echoes:
            source = localize("sonar.source.active_echo")
            stamp = float(echoes[-1]["t"])
        else:
            source = localize("sonar.source.active_ping")
            pending = getattr(sonar, "_pending_pings", [])
            if pending:
                stamp = max(float(item["sent_at"]) for item in pending)
    if stamp is None:
        return source, None, localize("sonar.evidence.absent")
    age = max(0.0, now - stamp)
    state = "sonar.evidence.stale" if age > 30.0 else "sonar.evidence.current"
    return source, age, localize(state)


def _detail_rows(game, page):
    """One content list supplies both detail height and drawing."""
    sonar = game.sonar
    contact = getattr(game, "selected_contact", None)
    title = ("sonar.analysis" if page == 2 else
             "sonar.environment_model" if page == 4 else
             "sonar.active_echoes" if page == 5 else "sonar.listening_post")
    rows = [(title, CYAN, 15)]
    source, evidence_age, evidence_state = _detail_evidence(game, page)
    rows.extend((line, color, 12) for line, color in (
        (message("sonar.line.evidence_source", source=source), TEXT),
        (message("sonar.line.evidence_age_state",
                 age=f"{evidence_age:.1f}s" if evidence_age is not None else "--",
                 state=evidence_state), TEXT),
        (message("sonar.line.operating", array=display_value(
            "array", getattr(game, "sonar_mode", "BOW")), state=localize(
            "sonar.track" if getattr(sonar, "focus_locked", False) else "ui.manual")), DIM),
    ))
    array_state = _array_state_line(game)
    if array_state is not None:
        # Replaces the former header chip: shown on every page while it matters.
        rows.append((array_state, AMBER, 12))
    tools = getattr(game, "sonar_tools", None)
    assist = bool(getattr(game, "operator_assist", lambda: True)())
    if page in (1, 2) and tools is not None:
        columns = list(getattr(sonar, "integration_columns", ()))
        if page == 1:
            values = (analysis_tools.integrate([c[0] for c in columns], tools.integration_s)
                      if columns else np.zeros(0))
            level = analysis_tools.level_at(values, _lofar_frequencies(len(values)),
                                            tools.lofar_cursor_hz) if len(values) else None
            cursor = tools.lofar_cursor_hz
        else:
            values = (analysis_tools.integrate([c[2] for c in columns], tools.integration_s)
                      if columns else np.zeros(0))
            level = analysis_tools.level_at(values, np.arange(1, len(values) + 1, dtype=float),
                                            tools.demon_cursor_hz) if len(values) else None
            cursor = tools.demon_cursor_hz
        rows.append((message("sonar.line.cursor", frequency=f"{cursor:.1f}",
                             level="--" if level is None else f"{level:.2f}",
                             seconds=tools.integration_s), CYAN, 13))
    if page == 2 and not assist:
        # Manual blade count from the operator's shaft (S) and blade (B) marks.
        result = analysis_tools.blade_count(tools.shaft_hz, tools.blade_hz)
        lines = [message("sonar.line.demon_marks",
                         shaft="--" if tools.shaft_hz is None else f"{tools.shaft_hz:.1f}",
                         blade="--" if tools.blade_hz is None else f"{tools.blade_hz:.1f}")]
        if result is not None:
            blades, deviation, rpm = result
            lines.append(message("sonar.line.blade_count", blades=blades,
                                 deviation=f"{deviation:+.2f}", rpm=f"{rpm:.0f}"))
        elif tools.shaft_hz is not None:
            lines.append(message("sonar.line.shaft_rpm", rpm=f"{tools.shaft_hz * 60:.0f}"))
        rows.extend((line, TEXT, 13) for line in lines)
        rows.extend(_library_rows(game))
        return rows
    if page == 2:
        _, analysis, evidence = _demon_evidence(sonar)
        if evidence:
            rate = analysis["blade_rate_hz"]
            lines = [message("sonar.line.observed_tonal", rate=f"{rate:.1f}", confidence=f"{analysis['confidence']:.0%}"),
                     message("sonar.line.rpm_pair", first=3, first_rpm=f"{rate * 20:.0f}", second=4, second_rpm=f"{rate * 15:.0f}"),
                     message("sonar.line.rpm_pair", first=5, first_rpm=f"{rate * 12:.0f}", second=6, second_rpm=f"{rate * 10:.0f}"),
                     message("sonar.line.rpm_last", blades=7, rpm=f"{rate * 60 / 7:.0f}")]
        else:
            lines = ["sonar.no_reliable_line", "sonar.derivation_pending"]
        rows.extend((line, TEXT, 13) for line in lines)
        rows.append(("sonar.catalog_reference", AMBER, 13))
        candidates = getattr(sonar, "signature_candidates", []) if evidence else []
        for i in range(3):
            name, score = "--", None
            if i < len(candidates):
                signature, score = candidates[i]
                name = getattr(signature, "label", str(signature))
            prefix = localize("sonar.best_reference") if i == 0 else localize(message("sonar.alternative", index=i))
            score_text = f"{score:.0%}" if score is not None else "--"
            rows.append((message("sonar.line.reference", prefix=prefix,
                                 name=f"{score_text} {name}"), TEXT, 13))
        return rows
    if page == 4:
        profile = getattr(sonar, "bt_profile", None)
        tow = _tow_status(sonar, getattr(_sonar_observer(game), "speed", 0.0))
        actual = float(tow.get("depth_m", config.SONAR_TOWED_DEPTH_M))
        target = float(tow.get("depth_target_m", actual))
        lines = [message("sonar.line.tow_status", state=display_value('tow', tow['state']),
                         payout=f"{tow['payout_percent']:.0f}",
                         stability=f"{tow['performance']:.0%}",
                         ready=localize("ui.ready" if tow["available"] else "ui.not_ready")),
                 message("sonar.line.depth_bt_ready", actual=f"{actual:.0f}",
                         target=f"{target:.0f}",
                         seconds=f"{getattr(sonar, 'bt_cooldown', 0):.0f}")]
        if profile:
            age = max(0.0, getattr(game, "sim_t", 0.0) - profile.get("t", 0.0))
            bands = profile.get("cz_bands_nm", [])
            band_text = ", ".join(f"{lo:.0f}-{hi:.0f}" for lo, hi in bands)
            lines += [message("sonar.line.bt_summary", age=f"{age:.0f}",
                              sea=profile.get('sea_state', '--'),
                              thermocline=f"{profile.get('thermocline_m', 0):.0f}",
                              depth=f"{profile.get('water_depth_m', 0):.0f}"),
                      message("sonar.line.cz", bands=band_text or '--')]
        else:
            lines += ["sonar.bt_not_measured", "sonar.measure_profile"]
        vds = _vds_status(sonar)
        if vds is not None and vds["state"] != "STOWED":
            # A lowered VDS takes the depth-hint row so the panel keeps its size.
            lines.append(message("sonar.line.vds_status", state=display_value('tow', vds['state']),
                                 payout=f"{vds['payout_percent']:.0f}",
                                 actual=f"{float(vds['depth_m']):.0f}",
                                 target=f"{float(vds['depth_target_m']):.0f}",
                                 ready=localize("ui.ready" if vds["available"] else "ui.not_ready")))
        else:
            lines += ["sonar.tas_depth_control"]
        if contact is not None:
            lines += [display_value("fusion", getattr(contact, "fusion_status", "KEINE FUSION"))]
            contact_range = getattr(contact, "range_est", None)
            if contact_range is not None and profile:
                in_cz = any(lo <= contact_range <= hi
                            for lo, hi in profile.get("cz_bands_nm", []))
                lines += [message("sonar.line.contact_cz", answer=localize("common.yes" if in_cz else "common.no"))]
            delta = getattr(contact, "fusion_delta_deg", None)
            if delta is not None:
                lines += [message("sonar.line.array_delta", delta=f"{delta:.1f}")]
            mirror = getattr(contact, "mirror_bearing", None)
            if getattr(contact, "towed_ambiguous", False) and mirror is not None:
                lines += [message("sonar.line.tas_mirror", mirror=f"{mirror:05.1f}")]
            tonal = getattr(contact, "tonal_hz", None)
            if tonal is not None:
                lines += [message("sonar.line.tonal", frequency=f"{tonal:.2f}")]
            ellipse = getattr(contact, "tma_ellipse", None)
            if ellipse is not None:
                lines += [message("sonar.line.tma_ellipse", major=f"{ellipse[0]:.1f}",
                                  minor=f"{ellipse[1]:.1f}",
                                  orientation=f"{ellipse[2]:03.0f}")]
        rows.extend((line, DIM, 13) for line in lines)
        return rows
    if page == 5:
        echoes = active_echoes(sonar, getattr(game, "sim_t", 0.0))
        newest = echoes[-1] if echoes else None
        lines = [message("sonar.line.echo_history", count=len(echoes), maximum=getattr(config, 'SONAR_ECHO_HISTORY_MAX', 80)),
                 message("sonar.line.time_window", seconds=f"{ACTIVE_HISTORY_WINDOW_S:.0f}")]
        if newest is not None:
            depth = newest.get("depth_m")
            depth_sigma = newest.get("depth_sigma_m")
            depth_text = (f"{float(depth):.0f} +/- {float(depth_sigma or 0):.0f} m"
                          if depth is not None else "--")
            lines += [message("sonar.line.newest_echo", contact=newest.get('contact_id', '--')),
                      message("sonar.line.echo_age_mode", age=f"{newest['age_s']:.1f}", mode=newest.get('mode', '--')),
                      message("sonar.tooltip.range_sigma", range=f"{float(newest['range_nm']):.2f}", sigma=f"{float(newest.get('range_sigma_nm', 0)):.2f}"),
                      message("sonar.line.bearing", bearing=f"{float(newest['bearing']) % 360:05.1f}"),
                      message("sonar.line.depth", depth=depth_text)]
        else:
            lines += ["sonar.no_echo_measurement", "sonar.active_ping_control"]
        rows.extend((line, DIM, 13) for line in lines)
        return rows
    bearing = getattr(sonar, "listen_bearing", 0.0) % 360
    rows.append((message("sonar.line.bearing_value", bearing=f"{bearing:05.1f}"), TEXT, 27))
    # LOFAR shows the beam width in its own beam/filter line.
    lines = [] if page == 1 else [message(
        "sonar.line.beam", width=f"{getattr(sonar, 'beam_width_deg', 12):.1f}",
        mode=localize("sonar.track" if getattr(sonar, "focus_locked", False) else "ui.manual"))]
    if page == 3:
        quality = getattr(contact, "tma_quality", 0.0)
        course, speed = getattr(contact, "tma_course", None), getattr(contact, "tma_speed", None)
        track = getattr(sonar, "_tracks", {}).get(getattr(contact, "target_id", None))
        summary = tma_observation_summary(track, getattr(game, "sim_t", 0.0), quality)
        rate = (f"{summary['rate']:+.2f} deg/min"
                if summary["rate"] is not None else "-- deg/min")
        age = f"{summary['age']:.0f}s" if summary["age"] is not None else "--"
        lines += [message("sonar.line.tma_state_rate", status=display_value('tma', summary['state']),
                          rate=rate, age=age),
                  message("sonar.line.tma_geometry_quality", legs=summary['legs'],
                          geometry=display_value("tma", summary['geometry']),
                          quality=f"{quality:.0%}"),
                  message("sonar.line.tma_motion",
                          course=f"{course % 360:05.1f}" if course is not None else "--",
                          speed=f"{speed:.1f}" if speed is not None else "--"),
                  ]
        closing_kn = tma_closing_rate_kn(
            _sonar_observer(game), getattr(contact, "bearing", 0.0), course, speed)
        lines.append(message(
            "sonar.line.tma_closing_rate",
            rate=f"{closing_kn:+.1f}" if closing_kn is not None else "--"))
        seen = getattr(contact, "tma_seen", None)
        if seen is not None:
            lines += [message("observation.fix_age", age=f"{max(0, game.sim_t - seen):.0f}")]
        # Operator hypothesis (Z/X course, Ctrl+Z/X speed, Q range, K accept).
        if contact is not None and hasattr(game, "tma_hypothesis"):
            hypothesis = game.tma_hypothesis(contact)
            lines.append(message("sonar.line.tma_hypothesis",
                                 course=f"{hypothesis.course:05.1f}",
                                 speed=f"{hypothesis.speed_kn:.1f}",
                                 range=f"{hypothesis.range_nm:.1f}"))
            evaluation = game.tma_evaluation(contact)
            lines.append("sonar.tma_hypothesis_pending" if evaluation is None else
                         message("sonar.line.tma_residuals",
                                 rms=f"{evaluation['rms_deg']:.1f}",
                                 trend=f"{evaluation['systematic_deg']:.1f}",
                                 fit=f"{evaluation['fit']:.0%}",
                                 observable=f"{evaluation['observability']:.0%}"))
            proposal = getattr(sonar, "tma_proposals", {}).get(contact.target_id)
            if proposal is not None and getattr(game, "operator_assist", lambda: False)():
                lines.append(message("sonar.line.tma_proposal",
                                     course=f"{proposal.course:05.1f}",
                                     speed=f"{proposal.speed:.1f}"))
    elif page == 1:
        peaks = getattr(getattr(sonar, "receiver", None), "peaks", [])
        lines += [message("sonar.line.beam_filter", width=f"{getattr(sonar, 'beam_width_deg', 12):.1f}",
                          low=f"{getattr(sonar, 'band_low_hz', 0):.0f}",
                          high=f"{getattr(sonar, 'band_high_hz', 300):.0f}",
                          notch=localize("ui.on" if getattr(sonar, "notch_enabled", False) else "ui.off"))]
        if assist and len(peaks):
            peak_text = " | ".join(f"{hz:.1f} Hz {level:.2f}" for hz, level in peaks[:3])
            lines += [message("sonar.line.received_peaks", peaks=peak_text)]
        elif assist:
            lines += ["sonar.no_stable_lines"]
        # Cursor keys are in the key row; notes about identification in F1.
        base = _selected_harmonic(game)
        if base is not None:
            lines += [message("sonar.line.harmonics", fundamental=f"{base:.1f}",
                              second=f"{base * 2:.1f}", third=f"{base * 3:.1f}")]
    else:
        # Legends and interpretation notes live in F1, not on the scope.
        lines.append(_ping_line(game))
    rows.extend((line, DIM, 13) for line in lines)
    return rows


def _array_state_line(game):
    """Towed or variable-depth array while it is moving or not yet ready."""
    sonar = game.sonar
    speed = getattr(_sonar_observer(game), "speed", 0.0)
    for name, status in (("VDS", _vds_status(sonar)), ("TAS", _tow_status(sonar, speed))):
        if status is None or status["state"] == "STOWED" or status["available"]:
            continue
        pause = (" " + localize(message("ui.pause"))
                 if not status["handling_ok"] and status["state"] in (
                     "DEPLOYING", "RETRIEVING") else "")
        return message("sonar.line.array_state", array=name,
                       state=display_message("tow", status["state"]),
                       payout=f"{status['payout_percent']:.0f}",
                       stability=f"{status['performance']:.0%}", pause=pause)
    return None


def _ping_line(game):
    sonar = game.sonar
    return (message("sonar.ping_echo") if getattr(sonar, "ping_active", False) else
            message("sonar.ping_ready") if getattr(sonar, "ping_ready", True) else
            message("sonar.ping_cooldown", seconds=
                    f"{getattr(sonar, 'ping_cooldown_remaining', 0):.0f}"))


def _draw_details(game, rect, page):
    rows = _detail_rows(game, page)
    reduction = 0
    while reduction < 5 and sum(
            layout.font(max(12, size - reduction)).get_height() + 1
            for _, _, size in rows) > rect.h - 20:
        reduction += 1
    y = rect.y + 10
    for text, color, size in rows:
        size = max(12, size - reduction)
        while size > 12 and layout.font(size).size(localize(text))[0] > rect.w - 26:
            size -= 1
        height = layout.font(size).get_height() + 1
        _text(game.screen, text, (rect.x + 13, y, rect.w - 26, height), color, size)
        y += height


def _draw_contacts(game, rect):
    screen = game.screen
    contacts, start, visible = _visible_contacts(game, rect)
    selected = getattr(game, "selected_contact", None)
    end = start + len(visible)
    _text(screen, localize(message("sonar.contacts_heading",
                                   first=start + 1 if contacts else 0,
                                   last=end, total=len(contacts))),
          (rect.x + 12, rect.y + 8, rect.w - 24, 20), CYAN, 13)
    if not contacts:
        _text(screen, "ui.no_observed_contacts", (rect.x + 12, rect.y + 36, rect.w - 24, 20), DIM, 13)
    with layout.clip_to(screen, rect):
        for contact, row_rect in _list_rows(game, rect, 0)[0]:
            y = row_rect.y
            layout.record_geometry("sonar-contact", row_rect,
                                   f"sonar:contact:{contact.id}")
            if contact is selected:
                pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE, row_rect)
                pygame.draw.rect(screen, CYAN, (row_rect.x, y, 3, row_rect.h))
            label = display_value("classification",
                                  getattr(contact, "player_class", None))
            profile = getattr(contact, "player_profile", None)
            if profile is not None and hasattr(game, "profile_name"):
                # The operator's catalog assignment from the F8 analyser.
                label = f"{label} / {game.profile_name(profile)}"
            release = localize("sonar.release.short_released"
                               if getattr(contact, "released_to_opz", False)
                               else "sonar.release.short_private")
            contact_line = (localize(message(
                "sonar.line.contact",
                contact=observations.contact_display_id(game, contact),
                label=label)) + " " + release)
            _text(screen, contact_line,
                  (rect.x + 14, y + 2, rect.w - 105, 19), TEXT, 14)
            _text(screen, message("sonar.line.bearing_value",
                                  bearing=observations.format_bearing(
                                      contact, _sonar_observer(game))),
                  (rect.right - 94, y + 2, 82, 19), CYAN, 13, "right")
            age = max(0, getattr(game, "sim_t", 0) - getattr(contact, "last_seen", 0))
            uncertainty = observations.bearing_uncertainty(contact)
            _text(screen, message("sonar.line.contact_quality", snr=f"{getattr(contact, 'snr', -99):+.1f}",
                                  confidence=f"{getattr(contact, 'confidence', 0):.0%}", age=f"{age:.0f}",
                                  uncertainty=f"{uncertainty:.1f}" if uncertainty is not None else "--"),
                   (rect.x + 14, y + 23, rect.w - 28, 17), DIM, 12)


def _draw_echo_list(game, rect):
    """ACTIVE side rail, deliberately independent of live contact objects."""
    screen = game.screen
    row_geometry, total = _list_rows(game, rect, 5)
    rows = [item for item, _ in row_geometry]
    _text(screen, message("sonar.line.echo_returns", count=len(rows), total=total),
          (rect.x + 12, rect.y + 8, rect.w - 24, 20), CYAN, 13)
    if not rows:
        _text(screen, "ui.no_echoes",
              (rect.x + 12, rect.y + 36, rect.w - 24, 20), DIM, 13)
        return
    with layout.clip_to(screen, rect):
        for echo, row_rect in row_geometry:
            y = row_rect.y
            layout.record_geometry("sonar-echo", row_rect,
                                   f"sonar:echo:{echo.get('contact_id', '')}")
            color = _echo_color(float(echo["age_s"]))
            _text(screen, message("sonar.line.echo_bearing", contact=echo.get('contact_id', '--'),
                                  bearing=f"{float(echo['bearing']) % 360:05.1f}"),
                  (rect.x + 14, y + 2, rect.w - 28, 19), color, 14)
            _text(screen, message("sonar.line.echo_range_age", range=f"{float(echo['range_nm']):.2f}",
                                  age=f"{echo['age_s']:.0f}", mode=echo.get('mode', '--')),
                  (rect.x + 14, y + 23, rect.w - 28, 17), DIM, 12)


@localized
def draw_sonar_view(game, tr=None) -> None:
    """Draw full-station analysis pages; simulation remains game-owned."""
    layout.configure_for(game)
    screen = game.screen
    translate = _translator(game, tr)
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    geometry = sonar_geometry(game, page)
    station = geometry["station"]
    with layout.clip_to(screen, station):
        screen.fill(NAVY, station)
        pygame.draw.line(screen, CYAN, station.topleft, (station.right - 1, station.y), 2)
        _text(screen, message("sonar.page_title", station=translate("station.sonar"),
                              page=display_value("sonar_page", PAGES[page], translate)),
              (station.x + 14, station.y + 9, 315, 29), TEXT, 21)
        for i, (name, tab) in enumerate(zip(PAGES, geometry["tabs"])):
            layout.record_geometry("sonar-tab", tab, f"sonar:tab:{i}")
            if i == page:
                pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE, tab)
                pygame.draw.line(screen, CYAN, tab.bottomleft, (tab.right - 1, tab.bottom), 2)
            _text(screen, display_value("sonar_page", name, translate),
                  tab.move(6, 3).inflate(-12, 0),
                   CYAN if i == page else DIM, 14)
        main, details, contacts = (geometry["main"], geometry["details"],
                                   geometry["contacts"])
        for role, rect in (("sonar-main", main), ("sonar-details", details),
                           ("sonar-contacts", contacts)):
            layout.record_geometry("region", rect, role)
            pygame.draw.rect(screen, PANEL, rect)
            pygame.draw.rect(screen, GRID, rect, 1)
        with layout.clip_to(screen, main):
            if page < 2:
                _draw_waterfall(game, main, page)
            elif page == 2:
                _draw_demon(game, main)
            elif page == 3:
                _draw_tma(game, main)
            elif page == 4:
                _draw_environment(game, main)
            else:
                _draw_active(game, main, tr)
        with layout.clip_to(screen, details):
            _draw_details(game, details, page)
        if page == 5:
            _draw_echo_list(game, contacts)
        else:
            _draw_contacts(game, contacts)
        for segment in geometry["footer"]:
            rect = segment["rect"]
            layout.record_geometry("sonar-action", rect,
                                   f"sonar:action:{segment['action']}")
            pygame.draw.rect(screen, PANEL, rect)
            pygame.draw.line(screen, GRID, rect.topright, rect.bottomright)
            layout.command_segment(screen, rect, *segment["text"], size=11)

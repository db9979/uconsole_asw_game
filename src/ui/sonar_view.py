"""Read-only sonar instruments. All plots use receiver data or observations."""

from collections import OrderedDict
from functools import lru_cache

import numpy as np
import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize, message as structured_message
from src.ui import layout


NAVY = (6, 13, 25)
PANEL = (10, 22, 37)
GRID = (24, 49, 65)
DIM = (119, 151, 169)
TEXT = (211, 229, 233)
CYAN = (79, 224, 202)
AMBER = (244, 190, 97)
PAGES = ("BROADBAND", "LOFAR", "DEMON", "TMA", "UMWELT/FUSION", "ACTIVE")
ACTIVE_HISTORY_WINDOW_S = 120.0
_WATERFALL_CACHE = OrderedDict()
_WATERFALL_CACHE_SCREEN = None


def message(key, **values):
    return localize(structured_message(key, **values))


def _observed_bearing(observation) -> float:
    value = getattr(observation, "smoothed_bearing", None)
    if value is None:
        value = getattr(observation, "bearing", 0.0)
    return float(value or 0.0) % 360.0


def _bearing_line(game, bearing) -> str:
    return layout.format_bearing_pair(
        bearing, getattr(getattr(game, "ship", None), "course", 0.0))


def sonar_hit_target(game, pos):
    """Return context for a plotted receiver datum or displayed observation."""
    layout.configure_for(game)
    station = pygame.Rect(config.STATION_RECT)
    if pos is None or not station.collidepoint(pos):
        return None
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    sonar = game.sonar
    body = pygame.Rect(station.x + 12, station.y + 73,
                       station.w - 24, station.h - 124)
    rail_w = min(350, max(240, round(body.w * .28)))
    main = pygame.Rect(body.x, body.y, body.w - rail_w - 12, body.h)
    rail = pygame.Rect(main.right + 12, body.y, rail_w, body.h)
    detail_h = min(254 if page in (2, 5) else 216, rail.h - 92)
    details = pygame.Rect(rail.x, rail.y, rail.w, detail_h)
    contacts_rect = pygame.Rect(rail.x, details.bottom + 8, rail.w,
                                rail.bottom - details.bottom - 8)
    if contacts_rect.collidepoint(pos):
        if page == 5:
            echoes = active_echoes(sonar, getattr(game, "sim_t", 0.0))
            latest = {}
            for echo in echoes:
                latest[echo.get("contact_id")] = echo
            rows = list(reversed(list(latest.values())[-max(
                1, (contacts_rect.h - 33) // 43):]))
            row = (int(pos[1]) - contacts_rect.y - 32) // 43
            if 0 <= row < len(rows):
                echo = rows[row]
                return layout.tooltip_payload(
                    message("sonar.tooltip.echo_title", contact=echo.get('contact_id', '--')),
                    _bearing_line(game, echo["bearing"]),
                    message("sonar.tooltip.range", range=f"{float(echo['range_nm']):.2f}"),
                    message("sonar.tooltip.uncertainty_age", uncertainty=f"{float(echo.get('range_sigma_nm', 0)):.2f}", age=f"{echo['age_s']:.1f}"),
                    message("sonar.tooltip.active_source", mode=echo.get('mode', '--')),
                    target_id=f"sonar:echo:{echo.get('contact_id', '')}")
        else:
            contacts = sorted(sonar.active_contacts(), key=lambda item: item.id)
            capacity = max(1, (contacts_rect.h - 33) // 43)
            selected = getattr(game, "selected_contact", None)
            index = next((i for i, item in enumerate(contacts) if item is selected), 0)
            start = max(0, min(index - capacity // 2, len(contacts) - capacity))
            visible = contacts[start:start + capacity]
            row = (int(pos[1]) - contacts_rect.y - 32) // 43
            if 0 <= row < len(visible):
                contact = visible[row]
                label = display_value("classification",
                                      getattr(contact, "player_class", None))
                return layout.tooltip_payload(
                    message("sonar.tooltip.contact_title", contact=f"{contact.id:02d}"),
                    _bearing_line(game, _observed_bearing(contact)),
                    message("sonar.tooltip.classification", classification=label),
                    message("sonar.tooltip.level_confidence", level=f"{getattr(contact, 'snr', -99):+.1f}", confidence=f"{getattr(contact, 'confidence', 0):.0%}"),
                    message("sonar.tooltip.track_age", age=f"{max(0, game.sim_t - getattr(contact, 'last_seen', 0)):.0f}"),
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
        plot = pygame.Rect(main.x + 57, main.y + 61, main.w - 83, main.h - 108)
        if page == 1:
            plot.y += 66
            plot.h -= 66
        if not plot.collidepoint(pos):
            return None
        axis = (pos[0] - plot.x) / max(1, plot.w - 1)
        if page == 0:
            bin_count = 180
            bin_index = round(axis * bin_count) % bin_count
            bearing = bin_index * (360.0 / bin_count)
            rows = getattr(sonar, "broadband_history", [])
            row = min(len(rows) - 1, max(0, round(
                (1.0 - (pos[1] - plot.y) / max(1, plot.h - 1)) * (len(rows) - 1))))
            level = float(rows[row][bin_index % len(rows[row])]) \
                if rows and len(rows[row]) else 0.0
            return layout.tooltip_payload(
                message("sonar.tooltip.broadband_bin"), _bearing_line(game, bearing),
                message("sonar.tooltip.relative_level", level=f"{level:.3f}"),
                message("tooltip.omni_sample"),
                target_id=f"sonar:broadband:{bearing:.1f}")
        frequency = axis * config.LOFAR_FMAX_HZ
        receiver = getattr(sonar, "receiver", None)
        spectrum = getattr(receiver, "spectrum", [])
        idx = (min(range(len(spectrum)),
                   key=lambda item: abs(config.lofar_bin_freq(item) - frequency))
               if len(spectrum) else 0)
        level = float(spectrum[idx]) if len(spectrum) else 0.0
        for tonal in getattr(receiver, "ownship_tonals", []):
            tonal_hz = float(tonal.get("frequency_hz", -999))
            if abs(frequency - tonal_hz) <= max(2.0, 600.0 / max(1, plot.w)):
                rpm = tonal.get("rpm")
                if rpm is None:
                    rpm = (config.SHIP_RPM_MIN + getattr(game.ship, "speed", 0.0)
                           * config.SHIP_RPM_PER_KN)
                return layout.tooltip_payload(
                    message("sonar.own_shaft"),
                    message("sonar.tooltip.frequency_rpm", frequency=f"{tonal_hz:.1f}", rpm=f"{float(rpm):.0f}"),
                    message("sonar.own_tonal"),
                    target_id="sonar:own-shaft")
        return layout.tooltip_payload(
            message("sonar.tooltip.lofar_bin"), message("sonar.tooltip.frequency_level", frequency=f"{frequency:.1f}", level=f"{level:.3f}"),
            message("sonar.tooltip.beam_source", bearing=_bearing_line(
                game, getattr(sonar, "listen_bearing", 0))),
            target_id=f"sonar:lofar:{frequency:.1f}")
    if page == 2:
        plot = pygame.Rect(main.x + 57, main.y + 68, main.w - 83,
                           main.h - 115)
        if not plot.collidepoint(pos):
            return None
        frequency = (pos[0] - plot.x) / max(1, plot.w - 1) * 80.0
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
        point = points[-1]
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
            echo = min(echoes, key=lambda item: abs(float(item["bearing"]) - 180.0))
            return layout.tooltip_payload(
                message("sonar.tooltip.active_echoes", count=len(echoes)),
                message("sonar.tooltip.latest_echo", contact=echo.get('contact_id', '--'), age=f"{echo['age_s']:.1f}"),
                _bearing_line(game, echo["bearing"]),
                message("sonar.tooltip.range_sigma", range=f"{float(echo['range_nm']):.2f}", sigma=f"{float(echo.get('range_sigma_nm', 0)):.2f}"),
                message("sonar.active_source"),
                target_id="sonar:active-plot")
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
    original = localize(text)
    text = original
    while text and font.size(text)[0] > rect.w:
        text = text[:-1]
    if text != original:
        text = text[:-3] + "..." if len(text) >= 3 else ""
    x = rect.x
    if align == "right":
        x = rect.right - font.size(text)[0]
    elif align == "center":
        x += (rect.w - font.size(text)[0]) // 2
    with layout.clip_to(screen, rect):
        screen.blit(font.render(text, True, color), (x, rect.y))


def waterfall_surface(rows, width, height, gain_db=0.0):
    """Oldest-first rows become a bitmap with newest at TOP; x is bin order.

    Zero input stays dark. Gain changes intensity, never time or frequency.
    The small row bitmap is scaled once, not drawn as thousands of rectangles.
    """
    width, height = max(1, int(width)), max(1, int(height))
    values = np.asarray(rows, dtype=np.float32)
    if values.size == 0:
        surface = pygame.Surface((width, height))
        surface.fill(NAVY)
        return surface
    values = np.nan_to_num(values, nan=0.0, posinf=1.0, neginf=0.0)
    values = np.clip(values[::-1] * 10.0 ** (gain_db / 20.0), 0.0, 1.0)
    # A navy-to-phosphor ramp leaves faint receiver noise visible, not invented.
    low, high = np.asarray(NAVY), np.asarray(CYAN)
    pixels = (low + values[..., None] ** .72 * (high - low)).astype(np.uint8)
    small = pygame.surfarray.make_surface(pixels.transpose(1, 0, 2))
    return pygame.transform.scale(small, (width, height))


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
    gain_db, band_low, band_high, notch_enabled, ship_speed = controls
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
        processed[:, notch] = raw[:, notch] * 0.15
    return processed


def _waterfall(game, page, rect):
    global _WATERFALL_CACHE_SCREEN
    if game.screen is not _WATERFALL_CACHE_SCREEN:
        _WATERFALL_CACHE.clear()
        _WATERFALL_CACHE_SCREEN = game.screen
    sonar = game.sonar
    receiver = getattr(sonar, "receiver", None)
    rows = getattr(sonar, "broadband_history" if page == 0 else "lofar_history", [])
    source_rows = rows
    live_fallback = not len(rows) and page == 1
    # No focus gate: an empty history may still have a live receiver spectrum.
    if not len(rows) and page == 1:
        current = getattr(receiver, "spectrum", [])
        rows = [current] if len(current) else []
    controls = (getattr(sonar, "gain_db", 0.0),
                getattr(sonar, "band_low_hz", 0.0),
                getattr(sonar, "band_high_hz", 300.0),
                getattr(sonar, "notch_enabled", False),
                getattr(getattr(game, "ship", None), "speed", 0.0))
    if live_fallback:
        history_token = (id(rows[0]), len(rows[0])) if rows else (None, 0)
    else:
        history_token = (id(source_rows), len(source_rows),
                         id(source_rows[0]) if len(source_rows) else None,
                         id(source_rows[-1]) if len(source_rows) else None)
    key = (id(sonar), page, rect.size, getattr(receiver, "sequence", None),
           controls, history_token)
    cached = _WATERFALL_CACHE.get(key)
    if cached is None:
        raw = np.asarray(rows, dtype=float)
        processed = rows
        if page == 1 and len(rows):
            process = getattr(sonar, "process_lofar_column", None)
            processed = _process_lofar_rows(raw, controls, process is not None)
            processed = np.asarray([_linear_lofar(row, rect.w) for row in processed])
        elif page == 0 and len(rows):
            processed = np.asarray([_circular_broadband(row, rect.w)
                                    for row in raw])
        # Fixed time scale from the first sample: empty history stays below it.
        bitmap = processed
        if (not live_fallback and len(processed)
                and len(processed) < config.LOFAR_HISTORY_COLS):
            bitmap = np.concatenate((np.zeros((config.LOFAR_HISTORY_COLS - len(processed),
                                               len(processed[0]))), processed))
        surface = waterfall_surface(bitmap, *rect.size,
                                    gain_db=controls[0] if page == 0 else 0.0)
        cached = (surface, processed)
        _WATERFALL_CACHE[key] = cached
        while len(_WATERFALL_CACHE) > 4:
            _WATERFALL_CACHE.popitem(last=False)
    _WATERFALL_CACHE.move_to_end(key)
    game.screen.blit(cached[0], rect)
    return cached[1]


def _grid(screen, rect, xmax, unit):
    divisions = 4 if xmax == 80 else 6
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


def _draw_active(game, panel, tr=None):
    """A-scope and bearing/range history made solely from echo_history."""
    screen, sonar = game.screen, game.sonar
    translate = _translator(game, tr)
    now = getattr(game, "sim_t", 0.0)
    echoes = active_echoes(sonar, now)
    latest = {}
    for echo in echoes:
        latest[echo.get("contact_id")] = echo

    _text(screen, translate("ACTIVE / ECHO-AUSWERTUNG"),
          (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    ready = bool(getattr(sonar, "ping_ready", True))
    remaining = float(getattr(sonar, "ping_cooldown_remaining",
                              getattr(sonar, "ping_cooldown", 0.0)))
    readiness = translate("BEREIT") if ready else f"{remaining:.0f}s"
    _text(screen, message("sonar.line.ping_history", ping=translate('PING'),
                          readiness=readiness, count=len(echoes),
                          window=translate('sonar.echo_window'), fade=translate('sonar.echo_fade')),
          (panel.x + 16, panel.y + 36, panel.w - 32, 20),
          CYAN if ready else AMBER, 13)

    gap = 18
    left_w = round((panel.w - 48 - gap) * .57)
    ascope = pygame.Rect(panel.x + 46, panel.y + 83, left_w, panel.h - 130)
    polar = pygame.Rect(ascope.right + gap, ascope.y,
                        panel.right - ascope.right - gap - 18, ascope.h)
    pygame.draw.rect(screen, NAVY, ascope)
    pygame.draw.rect(screen, NAVY, polar)
    max_range = max(5.0, max((float(e["range_nm"]) +
                              float(e.get("range_sigma_nm", 0.0))
                              for e in echoes), default=5.0))
    max_range = min(100.0, np.ceil(max_range / 5.0) * 5.0)

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
        distance = min(max_range, float(echo["range_nm"]))
        sigma = max(0.0, float(echo.get("range_sigma_nm", 0.0)))
        snr = float(echo.get("snr_db", 0.0))
        x = ascope.x + round(distance / max_range * (ascope.w - 1))
        half = round(sigma / max_range * (ascope.w - 1))
        height = round(np.clip((snr + 12.0) / 28.0, .08, 1.0) * (ascope.h - 12))
        color = _echo_color(float(echo["age_s"]))
        pygame.draw.line(screen, color, (x, ascope.bottom - 2),
                         (x, ascope.bottom - 2 - height), 2)
        pygame.draw.line(screen, AMBER, (x - half, ascope.bottom - 7),
                         (x + half, ascope.bottom - 7), 2)
        pygame.draw.circle(screen, color, (x, ascope.bottom - 2 - height), 4)

    center = polar.center
    radius = max(10, min(polar.w, polar.h) // 2 - 13)
    for fraction in (.25, .5, .75, 1.0):
        pygame.draw.circle(screen, GRID, center, round(radius * fraction), 1)
    pygame.draw.line(screen, GRID, (center[0], center[1] - radius),
                     (center[0], center[1] + radius))
    pygame.draw.line(screen, GRID, (center[0] - radius, center[1]),
                     (center[0] + radius, center[1]))
    _text(screen, translate("PEILUNG / ENTFERNUNG"),
          (polar.x, polar.y - 22, polar.w, 19), DIM, 13, "center")
    _text(screen, "N", (center[0] - 10, center[1] - radius, 20, 18), DIM, 12, "center")
    with layout.clip_to(screen, polar):
        for echo in echoes:
            bearing = np.deg2rad(float(echo["bearing"]))
            distance = min(max_range, float(echo["range_nm"]))
            sigma = max(0.0, float(echo.get("range_sigma_nm", 0.0)))
            color = _echo_color(float(echo["age_s"]))

            def point(value):
                radial = value / max_range * radius
                return (round(center[0] + np.sin(bearing) * radial),
                        round(center[1] - np.cos(bearing) * radial))

            pygame.draw.line(screen, AMBER, point(max(0.0, distance - sigma)),
                             point(min(max_range, distance + sigma)), 2)
            pygame.draw.circle(screen, color, point(distance), 3)
    if not echoes:
        _text(screen, translate("sonar.no_stored_echoes"),
              (panel.x + 60, panel.centery - 10, panel.w - 120, 22),
              AMBER, 14, "center")


def _draw_waterfall(game, panel, page):
    screen, sonar = game.screen, game.sonar
    title = "RUNDUM / BREITBAND" if page == 0 else "HOERSTRAHL / SCHMALBAND"
    _text(screen, title, (panel.x + 16, panel.y + 10, panel.w - 32, 23), CYAN, 16)
    plot = pygame.Rect(panel.x + 57, panel.y + 61, panel.w - 83, panel.h - 108)
    if page == 1:
        plot.y += 66
        plot.h -= 66
    if plot.w < 2 or plot.h < 2:
        return
    processed = _waterfall(game, page, plot)
    _grid(screen, plot, 360 if page == 0 else 300,
          "Peilung / deg" if page == 0 else "Hz / linear")
    _text(screen, "NEU", (panel.x + 8, plot.y, 45, 18), CYAN, 12)
    _text(screen, "ALT", (panel.x + 8, plot.bottom - 18, 45, 18), DIM, 12)
    times = getattr(sonar, "history_times" if page == 0 else "lofar_times", [])
    timing = (message("sonar.line.history_timed", newest=f"{times[-1]:.1f}",
                      oldest=f"{times[0]:.1f}", rows=len(processed)) if len(times) else
              message("sonar.line.history_untimed", rows=len(processed)))
    _text(screen, timing, (panel.x + 16, panel.y + 35, panel.w - 32, 20), DIM, 12)
    if not len(processed):
        _text(screen, "Noch keine Empfangsdaten", (plot.x, plot.centery - 10, plot.w, 22),
              DIM, 16, "center")
    if page == 0:
        bearing = getattr(sonar, "listen_bearing", 0.0) % 360
        half = getattr(sonar, "beam_width_deg", 12.0) / 2
        with layout.clip_to(screen, plot):
            for value in ((bearing - half) % 360, (bearing + half) % 360):
                x = plot.x + round(value / 360 * (plot.w - 1))
                pygame.draw.line(screen, DIM, (x, plot.y), (x, plot.bottom - 1))
            x = plot.x + round(bearing / 360 * (plot.w - 1))
            pygame.draw.line(screen, AMBER, (x, plot.y), (x, plot.bottom - 1))
        _text(screen, "Intensitaet: dunkel = leise / tuerkis = laut",
              (plot.x, plot.bottom + 24, plot.w - 160, 18), DIM, 12)
    else:
        spectrum_rect = pygame.Rect(plot.x, panel.y + 65, plot.w, 48)
        pygame.draw.rect(screen, NAVY, spectrum_rect)
        receiver = getattr(sonar, "receiver", None)
        current = getattr(receiver, "spectrum", [])
        process = getattr(sonar, "process_lofar_column", None)
        if len(current):
            latest = process(current, game.ship) if process else current
            latest = _linear_lofar(latest, plot.w)
        else:
            latest = processed[-1] if len(processed) else []
        _trace(screen, spectrum_rect, latest)
        held = getattr(sonar, "peak_hold", False)
        if held:
            peak = getattr(sonar, "peak_spectrum", getattr(receiver, "peak_spectrum", []))
            if peak is not None and len(peak):
                peak = process(peak, game.ship) if process else peak
                peak = _linear_lofar(peak, plot.w)
            else:
                peak = np.max(processed, axis=0) if len(processed) else []
            _trace(screen, spectrum_rect, peak, AMBER)
        legend = pygame.Rect(spectrum_rect.x + 5, spectrum_rect.y + 2, 160, 18)
        pygame.draw.rect(screen, NAVY, legend)
        _text(screen, "LIVE" + (" / MAX gehalten" if held else " / MAX aus"),
              legend, AMBER if held else DIM, 12)
        bearings = getattr(sonar, "lofar_bearings", [])
        note = (message("sonar.line.row_bearings", newest=f"{bearings[-1] % 360:05.1f}",
                        oldest=f"{bearings[0] % 360:05.1f}")
                if len(bearings) else message("sonar.line.history_bearing"))
        _text(screen, note, (plot.x, plot.bottom + 24, plot.w - 160, 18), DIM, 12)


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
    spectrum, _, evidence = _demon_evidence(game.sonar)
    _text(screen, "DEMON / HUELLENSPEKTRUM", (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    _text(screen, "Empfangene Modulation | relative Amplitude, keine Identifikation",
          (panel.x + 16, panel.y + 37, panel.w - 32, 20), DIM, 13)
    plot = pygame.Rect(panel.x + 57, panel.y + 68, panel.w - 83, panel.h - 115)
    pygame.draw.rect(screen, NAVY, plot)
    _grid(screen, plot, 80, "Hz / Huellkurve")
    for value in (0, .25, .5, .75, 1):
        y = plot.bottom - 1 - round(value * (plot.h - 1))
        pygame.draw.line(screen, GRID, (plot.x, y), (plot.right - 1, y))
        _text(screen, f"{value:.2f}", (panel.x + 6, y - 8, 45, 18), DIM, 12)
    if spectrum.size:
        # Receiver bins represent 1..80 Hz; add the zero-frequency baseline.
        _trace(screen, plot, np.concatenate(([0.0], spectrum)))
    if not evidence:
        _text(screen, "Zu wenig Evidenz fuer Blattfrequenz / RPM",
              (plot.x + 12, plot.y + 12, plot.w - 24, 22), AMBER, 14)


def _bearing_series(points):
    """Unwrap adjacent observed bearings so 359 -> 1 crosses north, not 180."""
    times = np.asarray([p.t for p in points], dtype=float)
    bearings = np.rad2deg(np.unwrap(np.deg2rad([p.bearing for p in points])))
    return times, bearings


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
        centered = times - float(np.mean(times))
        denom = float(np.dot(centered, centered))
        if denom > 0.0:
            rate = float(np.dot(centered, bearings - np.mean(bearings)) / denom * 60.0)

    leg_courses = []
    for point in points:
        course = getattr(point, "fcourse", None)
        if course is None:
            continue
        if (not leg_courses or abs(config.angle_diff_deg(course, leg_courses[-1]))
                >= config.TMA_MIN_COURSE_CHG_DEG):
            leg_courses.append(course)
    legs = len(leg_courses)
    course_span = (abs(config.angle_diff_deg(leg_courses[-1], leg_courses[0]))
                   if len(leg_courses) > 1 else 0.0)
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


def _draw_tma(game, panel):
    screen = game.screen
    contact = getattr(game, "selected_contact", None)
    track = getattr(game.sonar, "_tracks", {}).get(getattr(contact, "target_id", None))
    points = getattr(track, "pts", [])
    _text(screen, "TMA / BEOBACHTETE PEILUNGEN", (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    _text(screen, "Peilung ueber Sim-Zeit | Norddurchgang kontinuierlich | keine Weltpositionen",
          (panel.x + 16, panel.y + 37, panel.w - 32, 20), DIM, 12)
    plot = pygame.Rect(panel.x + 65, panel.y + 69, panel.w - 95, panel.h - 116)
    pygame.draw.rect(screen, NAVY, plot)
    times, bearings = _bearing_series(points)
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
    _text(screen, "Sim-Zeit / s", (plot.right - 140, plot.bottom + 24, 140, 18), DIM, 12, "right")
    if len(points):
        xy = [(plot.x + round((t - start) / (end - start) * (plot.w - 1)),
               plot.bottom - 1 - round((b - lo) / (hi - lo) * (plot.h - 1)))
              for t, b in zip(times, bearings)]
        with layout.clip_to(screen, plot):
            if len(xy) > 1:
                pygame.draw.lines(screen, CYAN, False, xy, 2)
            for point in xy:
                pygame.draw.circle(screen, TEXT, point, 3)
        _text(screen, message("sonar.line.observations", count=len(points),
                              duration=f"{times[-1] - times[0]:.1f}"),
               (plot.x, plot.bottom + 24, plot.w - 145, 18), DIM, 12)
        rate = (f"{summary['rate']:+.2f} deg/min"
                if summary["rate"] is not None else "-- deg/min")
        _text(screen, localize(message(
                      "sonar.tma_summary", rate=rate, legs=summary["legs"],
                      geometry=display_value("tma", summary["geometry"]),
                      state=display_value("tma", summary["state"]))),
              (plot.x + 8, plot.y + 8, plot.w - 16, 20),
              AMBER if summary["state"] != "LOESUNG STABIL" else CYAN, 13)
    else:
        _text(screen, "Keine Peilreihe / beobachteten Kontakt waehlen",
              (plot.x, plot.centery, plot.w, 22), DIM, 14, "center")


def _draw_environment(game, panel):
    """Draw only the operator-measured profile and observed array reports."""
    screen, sonar = game.screen, game.sonar
    _text(screen, "SCHALLPROFIL / SENSORFUSION",
          (panel.x + 16, panel.y + 10, panel.w - 32, 24), CYAN, 16)
    _text(screen, "Bathythermograph-Messung | HMS und TAS getrennt beobachtet",
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
    else:
        _text(screen, "Kein lokales Schallprofil",
              (plot.x, plot.centery - 20, plot.w, 22), AMBER, 16, "center")
        _text(screen, "E: Bathythermograph ausbringen",
              (plot.x, plot.centery + 8, plot.w, 20), DIM, 14, "center")

    max_depth = (float(max(profile.get("depths_m", [300]))) if profile else 300.0)
    tow = _tow_status(sonar, getattr(getattr(game, "ship", None), "speed", 0.0))
    actual = float(tow.get("depth_m", config.SONAR_TOWED_DEPTH_M))
    target = float(tow.get("depth_target_m", actual))
    ay = plot.y + round(min(actual, max_depth) / max_depth * (plot.h - 1))
    pygame.draw.line(screen, (120, 210, 170), (plot.x, ay), (plot.right - 1, ay), 1)
    _text(screen, message("sonar.line.tow", state=display_value('tow', tow['state']),
                          payout=f"{tow['payout_percent']:.0f}", actual=f"{actual:.0f}",
                          target=f"{target:.0f}"),
          (plot.right - 180, ay - 19, 172, 18), (120, 210, 170), 12, "right")

    y = plot.bottom + 29
    _text(screen, "ARRAY-VERGLEICH", (panel.x + 16, y, panel.w - 32, 20), CYAN, 14)
    y += 23
    contacts = sorted(sonar.active_contacts(), key=lambda contact: contact.id)
    for contact in contacts[:4]:
        reports = getattr(contact, "array_observations", {})
        bow, towed = reports.get("BOW"), reports.get("TOWED")
        bow_text = (f"{bow['bearing']:05.1f} / {bow['snr']:+.1f}dB"
                    if bow else "  --.- / --")
        towed_text = (f"{towed['bearing']:05.1f} / {towed['snr']:+.1f}dB"
                      if towed else "  --.- / --")
        status_raw = getattr(contact, "fusion_status", "KEINE DATEN")
        status = display_value("fusion", status_raw)
        color = (config.COLOR_OK if status_raw == "BESTAETIGT" else
                 config.COLOR_WARN if "DIVERGENT" in status_raw else DIM)
        _text(screen, message("sonar.line.array_contact", contact=f"{contact.id:02d}",
                              bow=bow_text, towed=towed_text, status=status),
              (panel.x + 20, y, panel.w - 40, 19), color, 12)
        y += 20
    if not contacts:
        _text(screen, "Keine beobachteten Kontakte fuer den Arrayvergleich",
              (panel.x + 20, y, panel.w - 40, 19), DIM, 13)


def _draw_details(game, rect, page):
    screen, sonar = game.screen, game.sonar
    x, y, w = rect.x + 13, rect.y + 10, rect.w - 26
    contact = getattr(game, "selected_contact", None)
    title = ("AUSWERTUNG" if page == 2 else
             "UMWELTMODELL" if page == 4 else
             "ACTIVE-ECHOS" if page == 5 else "HOERPOSTEN")
    _text(screen, title, (x, y, w, 22), CYAN, 15)
    y += 28
    if page == 2:
        _, analysis, evidence = _demon_evidence(sonar)
        if evidence:
            rate = analysis["blade_rate_hz"]
            lines = [message("sonar.line.observed_tonal", rate=f"{rate:.1f}", confidence=f"{analysis['confidence']:.0%}"),
                     "ABLEITUNG: RPM bei angenommener Blattzahl",
                     message("sonar.line.rpm_pair", first=3, first_rpm=f"{rate * 20:.0f}", second=4, second_rpm=f"{rate * 15:.0f}"),
                     message("sonar.line.rpm_pair", first=5, first_rpm=f"{rate * 12:.0f}", second=6, second_rpm=f"{rate * 10:.0f}"),
                     message("sonar.line.rpm_last", blades=7, rpm=f"{rate * 60 / 7:.0f}")]
        else:
            lines = ["BEOBACHTET: keine belastbare Linie",
                     "ABLEITUNG: ausstehend / mehr Evidenz erforderlich"]
        for line in lines:
            _text(screen, line, (x, y, w, 20), TEXT, 13)
            y += 21
        _text(screen, "REFERENZ: Katalog-Aehnlichkeit", (x, y + 2, w, 20), AMBER, 13)
        y += 25
        candidates = getattr(sonar, "signature_candidates", []) if evidence else []
        for i in range(3):
            name, score = "--", None
            if i < len(candidates):
                signature, score = candidates[i]
                name = getattr(signature, "label", str(signature))
            prefix = localize("sonar.best_reference") if i == 0 else localize(message("sonar.alternative", index=i))
            _text(screen, message("sonar.line.reference", prefix=prefix, name=name), (x, y, w - 51, 19), TEXT, 13)
            _text(screen, f"{score:.0%}" if score is not None else "--",
                  (x + w - 48, y, 48, 19), CYAN, 13, "right")
            y += 23
        return
    if page == 4:
        profile = getattr(sonar, "bt_profile", None)
        tow = _tow_status(sonar, getattr(getattr(game, "ship", None), "speed", 0.0))
        actual = float(tow.get("depth_m", config.SONAR_TOWED_DEPTH_M))
        target = float(tow.get("depth_target_m", actual))
        lines = [message("sonar.line.tow_short", state=display_value('tow', tow['state']), payout=f"{tow['payout_percent']:.0f}"),
                 localize(message("sonar.stability_ready",
                                  stability=f"{tow['performance']:.0%}",
                                  ready=localize("ui.ready" if tow["available"]
                                                 else "ui.not_ready"))),
                 localize(message("sonar.depth_target", actual=f"{actual:.0f}",
                                  target=f"{target:.0f}"))]
        if profile:
            age = max(0.0, getattr(game, "sim_t", 0.0) - profile.get("t", 0.0))
            bands = profile.get("cz_bands_nm", [])
            band_text = ", ".join(f"{lo:.0f}-{hi:.0f}" for lo, hi in bands)
            lines += [message("sonar.line.bt_age", age=f"{age:.0f}", sea=profile.get('sea_state', '--')),
                      message("sonar.line.thermocline", depth=f"{profile.get('thermocline_m', 0):.0f}"),
                      message("sonar.line.water_depth", depth=f"{profile.get('water_depth_m', 0):.0f}"),
                      message("sonar.line.cz", bands=band_text or '--')]
        else:
            lines += ["BT nicht gemessen", "E: Schallprofil messen"]
        lines += [message("sonar.line.bt_ready", seconds=f"{getattr(sonar, 'bt_cooldown', 0):.0f}"),
                  "U/V: TAS 10 m heben/senken"]
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
        for line in lines:
            _text(screen, line, (x, y, w, 21), DIM, 13)
            y += 23
        return
    if page == 5:
        echoes = active_echoes(sonar, getattr(game, "sim_t", 0.0))
        newest = echoes[-1] if echoes else None
        lines = [message("sonar.line.echo_history", count=len(echoes), maximum=getattr(config, 'SONAR_ECHO_HISTORY_MAX', 80)),
                 message("sonar.line.time_window", seconds=f"{ACTIVE_HISTORY_WINDOW_S:.0f}"),
                 "Gelb: +/- Entfernungssigma"]
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
            lines += ["Keine Echo-Messung", "A: Aktiv-Ping ausloesen"]
        for line in lines:
            _text(screen, line, (x, y, w, 21), DIM, 13)
            y += 23
        return
    bearing = getattr(sonar, "listen_bearing", 0.0) % 360
    _text(screen, message("sonar.line.bearing_value", bearing=f"{bearing:05.1f}"), (x, y, w, 34), TEXT, 27)
    y += 39
    lines = [message("sonar.line.beam", width=f"{getattr(sonar, 'beam_width_deg', 12):.1f}",
                     mode=localize("sonar.track" if getattr(sonar, "focus_locked", False) else "ui.manual"))]
    if page == 3:
        quality = getattr(contact, "tma_quality", 0.0)
        course, speed = getattr(contact, "tma_course", None), getattr(contact, "tma_speed", None)
        track = getattr(sonar, "_tracks", {}).get(getattr(contact, "target_id", None))
        summary = tma_observation_summary(track, getattr(game, "sim_t", 0.0), quality)
        rate = (f"{summary['rate']:+.2f} deg/min"
                if summary["rate"] is not None else "-- deg/min")
        age = f"{summary['age']:.0f}s" if summary["age"] is not None else "--"
        lines += [message("sonar.line.status", status=display_value('tma', summary['state'])),
                  localize(message("sonar.bearing_rate_age", rate=rate, age=age)),
                  message("sonar.line.geometry", legs=summary['legs'], geometry=summary['geometry']),
                  message("sonar.line.tma_quality", quality=f"{quality:.0%}"),
                  message("sonar.line.tma_course", course=f"{course % 360:05.1f}" if course is not None else "--"),
                  message("sonar.line.tma_speed", speed=f"{speed:.1f}" if speed is not None else "--"),
                  "Tiefe: nicht aus TMA ableitbar"]
    elif page == 1:
        peaks = getattr(getattr(sonar, "receiver", None), "peaks", [])
        lines += ["Empfangslinien / Hz : Pegel"]
        lines += [f"{hz:6.1f} Hz : {level:.2f}" for hz, level in peaks[:4]]
        if not len(peaks):
            lines += ["Keine stabilen Linien"]
        elif len(peaks) >= 2:
            frequencies = sorted(hz for hz, _ in peaks[:6])
            spacing = float(np.median(np.diff(frequencies)))
            lines += [message("sonar.line.spacing", spacing=f"{spacing:.1f}")]
        lines += ["Linien sind keine Identifikation"]
    else:
        lines += ["360 deg / passiver Empfang", "Rauschen bleibt sichtbar",
                  "Gelb: aktuelle Hoerpeilung", "Grau: Grenzen des Hoerstrahls",
                  "Kontaktklasse: nur Spielereingabe"]
    for line in lines:
        _text(screen, line, (x, y, w, 21), DIM, 13)
        y += 23


def _draw_contacts(game, rect):
    screen = game.screen
    contacts = sorted(game.sonar.active_contacts(), key=lambda c: c.id)
    selected = getattr(game, "selected_contact", None)
    capacity = max(1, (rect.h - 33) // 43)
    index = next((i for i, c in enumerate(contacts) if c is selected), 0)
    start = max(0, min(index - capacity // 2, len(contacts) - capacity))
    end = min(len(contacts), start + capacity)
    _text(screen, localize(message("sonar.contacts_heading",
                                   first=start + 1 if contacts else 0,
                                   last=end, total=len(contacts))),
          (rect.x + 12, rect.y + 8, rect.w - 24, 20), CYAN, 13)
    if not contacts:
        _text(screen, "Keine beobachteten Kontakte", (rect.x + 12, rect.y + 36, rect.w - 24, 20), DIM, 13)
    with layout.clip_to(screen, rect):
        for row, contact in enumerate(contacts[start:end]):
            y = rect.y + 32 + row * 43
            if contact is selected:
                pygame.draw.rect(screen, (21, 55, 68), (rect.x + 5, y, rect.w - 10, 41))
                pygame.draw.rect(screen, CYAN, (rect.x + 5, y, 3, 41))
            label = display_value("classification",
                                  getattr(contact, "player_class", None))
            _text(screen, message("sonar.line.contact", contact=f"{contact.id:02d}", label=label), (rect.x + 14, y + 2, rect.w - 105, 19), TEXT, 14)
            _text(screen, message("sonar.line.bearing_value", bearing=f"{_observed_bearing(contact):05.1f}"),
                  (rect.right - 94, y + 2, 82, 19), CYAN, 13, "right")
            age = max(0, getattr(game, "sim_t", 0) - getattr(contact, "last_seen", 0))
            _text(screen, message("sonar.line.contact_quality", snr=f"{getattr(contact, 'snr', -99):+.1f}",
                                  confidence=f"{getattr(contact, 'confidence', 0):.0%}", age=f"{age:.0f}"),
                   (rect.x + 14, y + 23, rect.w - 28, 17), DIM, 12)


def _draw_echo_list(game, rect):
    """ACTIVE side rail, deliberately independent of live contact objects."""
    screen = game.screen
    echoes = active_echoes(game.sonar, getattr(game, "sim_t", 0.0))
    latest = {}
    for echo in echoes:
        latest[echo.get("contact_id")] = echo
    rows = list(latest.values())
    capacity = max(1, (rect.h - 33) // 43)
    rows = rows[-capacity:]
    _text(screen, message("sonar.line.echo_returns", count=len(rows), total=len(latest)),
          (rect.x + 12, rect.y + 8, rect.w - 24, 20), CYAN, 13)
    if not rows:
        _text(screen, "Keine Echo-Messungen",
              (rect.x + 12, rect.y + 36, rect.w - 24, 20), DIM, 13)
        return
    with layout.clip_to(screen, rect):
        for row, echo in enumerate(reversed(rows)):
            y = rect.y + 32 + row * 43
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
    station = pygame.Rect(config.STATION_RECT)
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    sonar = game.sonar
    with layout.clip_to(screen, station):
        screen.fill(NAVY, station)
        pygame.draw.line(screen, CYAN, station.topleft, (station.right - 1, station.y), 2)
        _text(screen, translate("station.sonar") + " / " +
              display_value("sonar_page", PAGES[page], translate),
              (station.x + 14, station.y + 9, 315, 29), TEXT, 21)
        tab_x = station.x + 348
        tab_w = max(50, (station.w - 362) // len(PAGES))
        for i, name in enumerate(PAGES):
            tab = pygame.Rect(tab_x + i * tab_w, station.y + 9, tab_w - 5, 27)
            if i == page:
                pygame.draw.rect(screen, (21, 55, 68), tab)
                pygame.draw.line(screen, CYAN, tab.bottomleft, (tab.right - 1, tab.bottom), 2)
            _text(screen, display_value("sonar_page", name, translate),
                  tab.move(6, 3).inflate(-12, 0),
                   CYAN if i == page else DIM, 14)
        mode = getattr(game, 'sonar_mode', 'BOW')
        tow = _tow_status(sonar, getattr(getattr(game, "ship", None), "speed", 0.0))
        tow_pause = (" " + localize(message("ui.pause"))
                     if not tow["handling_ok"] and tow["state"] in (
                         "DEPLOYING", "RETRIEVING") else "")
        tow_ready = (localize(message("ui.ready")) if tow["available"] else
                     localize(message("sonar.stability",
                                      value=f"{tow['performance']:.0%}")))
        ping = (localize(message("sonar.ping_echo")) if getattr(sonar, "ping_active", False) else
                localize(message("sonar.ping_ready")) if getattr(sonar, "ping_ready", True) else
                localize(message("sonar.ping_cooldown", seconds=
                                 f"{getattr(sonar, 'ping_cooldown_remaining', 0):.0f}")))
        statuses = (
            localize(message("sonar.status.array", array=display_value("array", mode),
                             state=display_value("tow", tow["state"]),
                             payout=f"{tow['payout_percent']:.0f}", ready=tow_ready,
                             pause=tow_pause)),
            localize(message("sonar.status.listen",
                             bearing=f"{getattr(sonar, 'listen_bearing', 0) % 360:05.1f}",
                             gain=f"{getattr(sonar, 'gain_db', 0):+.0f}")),
            localize(message("sonar.status.filter",
                             low=f"{getattr(sonar, 'band_low_hz', 0):.0f}",
                             high=f"{getattr(sonar, 'band_high_hz', 300):.0f}",
                             notch=localize("ui.on" if getattr(sonar, "notch_enabled", False)
                                            else "ui.off"), ping=ping)),
        )
        status_w = (station.w - 28) // 3
        for i, status in enumerate(statuses):
            status_rect = pygame.Rect(station.x + 14 + i * status_w,
                                      station.y + 43, status_w - 8, 23)
            pygame.draw.rect(screen, PANEL, status_rect)
            _text(screen, status, status_rect.move(7, 3).inflate(-14, 0),
                  CYAN if i == 0 else DIM, 13)
        body = pygame.Rect(station.x + 12, station.y + 73, station.w - 24, station.h - 124)
        rail_w = min(350, max(240, round(body.w * .28)))
        main = pygame.Rect(body.x, body.y, body.w - rail_w - 12, body.h)
        rail = pygame.Rect(main.right + 12, body.y, rail_w, body.h)
        detail_h = min(254 if page in (2, 5) else 216, rail.h - 92)
        details = pygame.Rect(rail.x, rail.y, rail.w, detail_h)
        contacts = pygame.Rect(rail.x, details.bottom + 8, rail.w, rail.bottom - details.bottom - 8)
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
        footer = ("SEITE Bild auf/ab   KONTAKT Auf/Ab   STRAHL R + Links/Rechts   TRACK Enter   PING A   ZIEL M",
                  "TAS Y Ausbringen/Einholen   B Array   U/V Tiefe   E BT   I/O Gain   F Band   N Notch   J Audio")
        for i, line in enumerate(footer):
            _text(screen, translate(line),
                  (station.x + 14, station.bottom - 42 + i * 21,
                   station.w - 28, 19), DIM, 13)

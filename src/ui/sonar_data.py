"""Data side of the sonar instruments: the observations, histories, array
states, spectra, peaks and TMA summaries the sonar pages plot, without
drawing.  Moved verbatim from ``sonar_view.py``, which re-exports every
name (the palette and ``_text`` stay there; the theme swaps them live).
"""

import math
from functools import lru_cache

import numpy as np
import pygame

from src.core import config
from src.core.i18n import (
    display_message, display_value, localize, message as structured_message)
from src.ui import layout
from src.ui import observations
from src.physics import ship_dynamics


PAGES = ("BROADBAND", "LOFAR", "DEMON", "TMA", "UMWELT/FUSION", "ACTIVE")
ACTIVE_HISTORY_WINDOW_S = 120.0
DEMON_DISPLAY_MAX_HZ = 50.0


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


def _history_for_page(sonar, page):
    if page == 0 and getattr(sonar, "broadband_long_history", None):
        return sonar.broadband_long_history, sonar.broadband_long_times, \
            config.SONAR_BROADBAND_LONG_ROWS
    if page == 0:
        return (getattr(sonar, "broadband_history", []),
                getattr(sonar, "history_times", []), config.LOFAR_HISTORY_COLS)
    return (getattr(sonar, "lofar_history", []),
            getattr(sonar, "lofar_times", []), config.LOFAR_HISTORY_COLS)


# Contact cards in the left column: card height and pitch (UI grid).
CARD_H = 62
CARD_PITCH = 66


def _visible_contacts(game, rect):
    contacts = sorted(game.sonar.active_contacts(), key=lambda item: item.id)
    capacity = max(1, (rect.h - 33) // CARD_PITCH)
    selected = getattr(game, "selected_contact", None)
    index = next((i for i, item in enumerate(contacts) if item is selected), 0)
    start = max(0, min(index - capacity // 2, len(contacts) - capacity))
    return contacts, start, contacts[start:start + capacity]


def _visible_echoes(game, rect):
    latest = {}
    for echo in active_echoes(game.sonar, getattr(game, "sim_t", 0.0)):
        latest[echo.get("contact_id")] = echo
    capacity = max(1, (rect.h - 33) // CARD_PITCH)
    return list(reversed(list(latest.values())[-capacity:])), len(latest)


def _list_rows(game, rect, page):
    """Return the exact visible row payloads and painted hit rectangles."""
    if page == 5:
        rows, total = _visible_echoes(game, rect)
    else:
        _, _, rows = _visible_contacts(game, rect)
        total = None
    return [(item, pygame.Rect(rect.x + 5, rect.y + 32 + index * CARD_PITCH,
                               rect.w - 10, CARD_H))
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


@lru_cache(maxsize=16)
def _interp_plan(xp_key: tuple, width: int, low: float, high: float):
    """How ``np.interp`` maps ``xp_key`` onto ``width`` points over
    [low, high]: per point the left sample, its offset, the sample spacing,
    and which points take a sample exactly or clamp (bounded, read-only)."""
    xp = np.asarray(xp_key, dtype=float)
    x = np.linspace(low, high, width)
    last = len(xp) - 1
    index = np.clip(np.searchsorted(xp, x, side="right") - 1, 0, last)
    inner = np.minimum(index, last - 1)
    offset = x - xp[inner]
    spacing = xp[inner + 1] - xp[inner]
    exact = (x == xp[index]) | (index == last)
    plan = (inner, offset, spacing, exact, index, x < xp[0], x > xp[-1])
    for array in plan:
        array.setflags(write=False)
    return plan


def _interp_rows(rows: np.ndarray, plan) -> np.ndarray:
    """``np.interp`` of every row with the same arithmetic (bit-identical):
    ``slope * (x - xp[j]) + f[j]``, exact samples and clamped ends."""
    inner, offset, spacing, exact, index, below, above = plan
    left = rows[:, inner]
    out = (rows[:, inner + 1] - left) / spacing * offset + left
    out[:, exact] = rows[:, index[exact]]
    out[:, below] = rows[:, :1]
    out[:, above] = rows[:, -1:]
    return out


def circular_broadband_rows(raw, width):
    """``_circular_broadband`` of every row of a history at once."""
    raw = np.asarray(raw, dtype=float)
    width = max(1, int(width))
    if raw.ndim != 2 or raw.shape[1] == 0:
        return np.asarray([_circular_broadband(row, width) for row in raw])
    wrapped = np.concatenate((raw, raw[:, :1]), axis=1)
    return _interp_rows(wrapped, _interp_plan(
        tuple(range(raw.shape[1] + 1)), width, 0.0, float(raw.shape[1])))


def linear_lofar_rows(raw, width):
    """``_linear_lofar`` of every row of a history at once."""
    raw = np.asarray(raw, dtype=float)
    if raw.ndim != 2 or raw.shape[1] < 2:
        return np.asarray([_linear_lofar(row, width) for row in raw])
    frequencies = _lofar_frequencies(raw.shape[1])
    return _interp_rows(raw, _interp_plan(
        tuple(float(value) for value in frequencies), int(width), 0.0,
        float(config.LOFAR_FMAX_HZ)))


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
        shaft = ship_dynamics.own_blade_line_hz(ship_speed)
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


def _selected_harmonic(game):
    """The operator's fundamental (placed with the cursor), if any."""
    selected = getattr(game, "sonar_harmonic_hz", None)
    if selected is None or not np.isfinite(selected) or selected <= 0:
        return None
    return float(selected)


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


def _console_lamps(game):
    """Ping, audio and peak hold as annunciator lamps (display only)."""
    sonar = game.sonar
    ping = ("caution" if getattr(sonar, "ping_active", False) else
            "on" if getattr(sonar, "ping_ready", True) else "off")
    # A click on a lamp presses its key (Shift+A ping, J audio, Space peak hold).
    return (("sonar.lamp.ping", "", ping, "Shift+A"),
            ("sonar.lamp.audio", "", "on" if getattr(game, "sonar_audio_enabled", False)
             else "off", "J"),
            ("sonar.lamp.peak", "", "caution" if getattr(sonar, "peak_hold", False)
             else "off", "Space"))

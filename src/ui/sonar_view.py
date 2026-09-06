"""Read-only sonar instruments. All plots use receiver data or observations."""

from collections import OrderedDict

import numpy as np
import pygame

from src.core import config
from src.ui import layout


NAVY = (6, 13, 25)
PANEL = (10, 22, 37)
GRID = (24, 49, 65)
DIM = (119, 151, 169)
TEXT = (211, 229, 233)
CYAN = (79, 224, 202)
AMBER = (244, 190, 97)
PAGES = ("BROADBAND", "LOFAR", "DEMON", "TMA", "UMWELT/FUSION")
_WATERFALL_CACHE = OrderedDict()


def _text(screen, text, rect, color=TEXT, size=14, align="left"):
    """One readable line, ellipsized rather than shrunk into microtext."""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    font = layout.font(size)
    original = str(text)
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


def _linear_lofar(row, width):
    """Interpolate the existing 1/2/5 Hz bins onto an honest linear Hz axis."""
    if len(row) == 0:
        return np.zeros(width)
    frequencies = [config.lofar_bin_freq(i) for i in range(len(row))]
    return np.interp(np.linspace(0.0, config.LOFAR_FMAX_HZ, width),
                     frequencies, row)


def _waterfall(game, page, rect):
    sonar = game.sonar
    receiver = getattr(sonar, "receiver", None)
    rows = getattr(sonar, "broadband_history" if page == 0 else "lofar_history", [])
    live_fallback = not len(rows) and page == 1
    # No focus gate: an empty history may still have a live receiver spectrum.
    if not len(rows) and page == 1:
        current = getattr(receiver, "spectrum", [])
        rows = [current] if len(current) else []
    raw = np.asarray(rows, dtype=np.float32)
    controls = (getattr(sonar, "gain_db", 0.0),
                getattr(sonar, "band_low_hz", 0.0),
                getattr(sonar, "band_high_hz", 300.0),
                getattr(sonar, "notch_enabled", False),
                getattr(getattr(game, "ship", None), "speed", 0.0))
    key = (id(sonar), page, rect.size, getattr(receiver, "sequence", None),
           controls, raw.shape, raw.tobytes())
    cached = _WATERFALL_CACHE.get(key)
    if cached is None:
        processed = rows
        if page == 1 and len(rows):
            process = getattr(sonar, "process_lofar_column", None)
            processed = [process(row, game.ship) if process else
                         np.clip(np.asarray(row) * 10 ** (controls[0] / 20), 0, 1)
                         for row in rows]
            processed = np.asarray([_linear_lofar(row, rect.w) for row in processed])
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
        _text(screen, label, (x - 24, rect.bottom + 5, 48, 19), DIM, 12, "center")
    _text(screen, unit, (rect.right - 150, rect.bottom + 24, 150, 18), DIM, 12, "right")
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
    timing = (f"Sim {times[-1]:.1f}s -> {times[0]:.1f}s | "
              f"{len(processed)} Zeilen" if len(times) else
              f"{len(processed)} Zeilen | Zeitstempel nicht verfuegbar")
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
        note = (f"Zeilenpeilung: neu {bearings[-1] % 360:05.1f} / alt {bearings[0] % 360:05.1f} deg"
                if len(bearings) else "Historie behaelt ihre Aufnahmepeilung")
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
        _text(screen, f"{len(points)} Messpunkte / {times[-1] - times[0]:.1f}s Beobachtung",
              (plot.x, plot.bottom + 24, plot.w - 145, 18), DIM, 12)
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
        _text(screen, f"Sprungschicht ~{thermo:.0f} m",
              (plot.x + 8, ty - 20, 210, 18), AMBER, 12)
        _text(screen, f"Schallgeschwindigkeit {lo:.1f}-{hi:.1f} m/s (Modell)",
              (plot.x, plot.bottom + 5, plot.w, 18), DIM, 12)
    else:
        _text(screen, "Kein lokales Schallprofil",
              (plot.x, plot.centery - 20, plot.w, 22), AMBER, 16, "center")
        _text(screen, "E: Bathythermograph ausbringen",
              (plot.x, plot.centery + 8, plot.w, 20), DIM, 14, "center")

    max_depth = (float(max(profile.get("depths_m", [300]))) if profile else 300.0)
    actual = getattr(sonar, "towed_depth_m", config.SONAR_TOWED_DEPTH_M)
    target = getattr(sonar, "towed_depth_target_m", actual)
    ay = plot.y + round(min(actual, max_depth) / max_depth * (plot.h - 1))
    pygame.draw.line(screen, (120, 210, 170), (plot.x, ay), (plot.right - 1, ay), 1)
    _text(screen, f"TAS {actual:.0f}m -> {target:.0f}m",
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
        status = getattr(contact, "fusion_status", "KEINE DATEN")
        color = (config.COLOR_OK if status == "BESTAETIGT" else
                 config.COLOR_WARN if "DIVERGENT" in status else DIM)
        _text(screen, f"K{contact.id:02d} HMS {bow_text} | TAS {towed_text} | {status}",
              (panel.x + 20, y, panel.w - 40, 19), color, 12)
        y += 20
    if not contacts:
        _text(screen, "Keine beobachteten Kontakte fuer den Arrayvergleich",
              (panel.x + 20, y, panel.w - 40, 19), DIM, 13)


def _draw_details(game, rect, page):
    screen, sonar = game.screen, game.sonar
    x, y, w = rect.x + 13, rect.y + 10, rect.w - 26
    contact = getattr(game, "selected_contact", None)
    title = "AUSWERTUNG" if page == 2 else \
        ("UMWELTMODELL" if page == 4 else "HOERPOSTEN")
    _text(screen, title, (x, y, w, 22), CYAN, 15)
    y += 28
    if page == 2:
        _, analysis, evidence = _demon_evidence(sonar)
        if evidence:
            rate = analysis["blade_rate_hz"]
            lines = [f"Blattfrequenz? {rate:.1f} Hz | {analysis['confidence']:.0%}",
                     "RPM-Hypothesen / angenommene Blaetter",
                     f"3: {rate * 20:.0f} RPM    4: {rate * 15:.0f} RPM",
                      f"5: {rate * 12:.0f} RPM    6: {rate * 10:.0f} RPM",
                      f"7: {rate * 60 / 7:.0f} RPM | Modellhypothesen"]
        else:
            lines = ["Keine belastbare Blattfrequenz", "RPM: -- / mehr Evidenz erforderlich"]
        for line in lines:
            _text(screen, line, (x, y, w, 20), TEXT, 13)
            y += 21
        _text(screen, "Aehnlichkeit / keine Identifikation", (x, y + 2, w, 20), AMBER, 13)
        y += 25
        candidates = getattr(sonar, "signature_candidates", []) if evidence else []
        for i in range(3):
            name, score = "--", None
            if i < len(candidates):
                signature, score = candidates[i]
                name = getattr(signature, "label", str(signature))
            _text(screen, f"{i + 1}. {name}", (x, y, w - 51, 19), TEXT, 13)
            _text(screen, f"{score:.0%}" if score is not None else "--",
                  (x + w - 48, y, 48, 19), CYAN, 13, "right")
            y += 23
        return
    if page == 4:
        profile = getattr(sonar, "bt_profile", None)
        actual = getattr(sonar, "towed_depth_m", config.SONAR_TOWED_DEPTH_M)
        target = getattr(sonar, "towed_depth_target_m", actual)
        lines = [f"TAS Tiefe {actual:.0f} m | Soll {target:.0f} m"]
        if profile:
            age = max(0.0, getattr(game, "sim_t", 0.0) - profile.get("t", 0.0))
            bands = profile.get("cz_bands_nm", [])
            band_text = ", ".join(f"{lo:.0f}-{hi:.0f}" for lo, hi in bands)
            lines += [f"BT Alter {age:.0f} s | See {profile.get('sea_state', '--')}",
                      f"Sprungschicht ~{profile.get('thermocline_m', 0):.0f} m",
                      f"Wassertiefe ~{profile.get('water_depth_m', 0):.0f} m",
                      f"CZ Prognose {band_text or '--'} NM"]
        else:
            lines += ["BT nicht gemessen", "E: Schallprofil messen"]
        lines += [f"BT Bereitschaft {getattr(sonar, 'bt_cooldown', 0):.0f} s",
                  "U/V: TAS 10 m heben/senken"]
        if contact is not None:
            lines += [getattr(contact, "fusion_status", "KEINE FUSION")]
            contact_range = getattr(contact, "range_est", None)
            if contact_range is not None and profile:
                in_cz = any(lo <= contact_range <= hi
                            for lo, hi in profile.get("cz_bands_nm", []))
                lines += ["Kontakt in CZ-Band? " + ("JA" if in_cz else "NEIN")]
            delta = getattr(contact, "fusion_delta_deg", None)
            if delta is not None:
                lines += [f"Array-Differenz {delta:.1f} deg"]
        for line in lines:
            _text(screen, line, (x, y, w, 21), DIM, 13)
            y += 23
        return
    bearing = getattr(sonar, "listen_bearing", 0.0) % 360
    _text(screen, f"{bearing:05.1f} deg", (x, y, w, 34), TEXT, 27)
    y += 39
    lines = [f"Strahl {getattr(sonar, 'beam_width_deg', 12):.1f} deg | "
             + ("TRACK" if getattr(sonar, "focus_locked", False) else "MANUELL")]
    if page == 3:
        quality = getattr(contact, "tma_quality", 0.0)
        course, speed = getattr(contact, "tma_course", None), getattr(contact, "tma_speed", None)
        lines += [f"TMA Qualitaet {quality:.0%}",
                  f"Kurs {course % 360:05.1f} deg (TMA)" if course is not None else "Kurs -- (TMA)",
                  f"Fahrt {speed:.1f} kn (TMA)" if speed is not None else "Fahrt -- (TMA)",
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
            lines += [f"Linienabstand ~{spacing:.1f} Hz (Hypothese)"]
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
    _text(screen, f"KONTAKTE  {start + 1 if contacts else 0}-{end}/{len(contacts)}  Up/Down",
          (rect.x + 12, rect.y + 8, rect.w - 24, 20), CYAN, 13)
    if not contacts:
        _text(screen, "Keine beobachteten Kontakte", (rect.x + 12, rect.y + 36, rect.w - 24, 20), DIM, 13)
    with layout.clip_to(screen, rect):
        for row, contact in enumerate(contacts[start:end]):
            y = rect.y + 32 + row * 43
            if contact is selected:
                pygame.draw.rect(screen, (21, 55, 68), (rect.x + 5, y, rect.w - 10, 41))
                pygame.draw.rect(screen, CYAN, (rect.x + 5, y, 3, 41))
            label = config.PLAYER_CLASS_LABELS.get(getattr(contact, "player_class", None), "Unbekannt")
            _text(screen, f"K{contact.id:02d}  {label}", (rect.x + 14, y + 2, rect.w - 105, 19), TEXT, 14)
            _text(screen, f"{getattr(contact, 'bearing', 0) % 360:05.1f} deg",
                  (rect.right - 94, y + 2, 82, 19), CYAN, 13, "right")
            age = max(0, getattr(game, "sim_t", 0) - getattr(contact, "last_seen", 0))
            _text(screen, f"SNR {getattr(contact, 'snr', -99):+.1f} dB | "
                  f"{getattr(contact, 'confidence', 0):.0%} | Alter {age:.0f}s",
                  (rect.x + 14, y + 23, rect.w - 28, 17), DIM, 12)


def draw_sonar_view(game) -> None:
    """Draw full-station analysis pages; simulation remains game-owned."""
    screen = game.screen
    station = pygame.Rect(config.STATION_RECT)
    page = int(getattr(game, "sonar_page", 0)) % len(PAGES)
    sonar = game.sonar
    with layout.clip_to(screen, station):
        screen.fill(NAVY, station)
        pygame.draw.line(screen, CYAN, station.topleft, (station.right - 1, station.y), 2)
        _text(screen, "SONAR / " + PAGES[page], (station.x + 14, station.y + 9, 315, 29), TEXT, 21)
        tab_x = station.x + 348
        tab_w = max(50, (station.w - 362) // len(PAGES))
        for i, name in enumerate(PAGES):
            tab = pygame.Rect(tab_x + i * tab_w, station.y + 9, tab_w - 5, 27)
            if i == page:
                pygame.draw.rect(screen, (21, 55, 68), tab)
                pygame.draw.line(screen, CYAN, tab.bottomleft, (tab.right - 1, tab.bottom), 2)
            _text(screen, name, tab.move(6, 3).inflate(-12, 0),
                  CYAN if i == page else DIM, 14)
        audio = ("N/A" if not getattr(getattr(game, "audio", None), "available", False)
                 else "AN" if getattr(game, "sonar_audio_enabled", False) else "AUS")
        mode = getattr(game, 'sonar_mode', 'BOW')
        depth_status = (f" {getattr(sonar, 'towed_depth_m', config.SONAR_TOWED_DEPTH_M):.0f}m"
                        if mode == "TOWED" else "")
        ping = ("PING ECHO" if getattr(sonar, "ping_active", False) else
                "PING BEREIT" if getattr(sonar, "ping_ready", True) else
                f"PING {getattr(sonar, 'ping_cooldown_remaining', 0):.0f}s")
        status = (f"{mode}{depth_status} | {ping} | "
                  f"Peilung {getattr(sonar, 'listen_bearing', 0) % 360:05.1f} deg | "
                  f"Gain {getattr(sonar, 'gain_db', 0):+.0f} dB | "
                  f"Band {getattr(sonar, 'band_low_hz', 0):.0f}-{getattr(sonar, 'band_high_hz', 300):.0f} Hz | "
                  f"Notch {'AN' if getattr(sonar, 'notch_enabled', False) else 'AUS'} | "
                   f"Audio {audio} {getattr(game, 'sonar_volume', 0):.0%} "
                   + ("BAND" if getattr(sonar, "listen_filtered", False) else "BREIT"))
        _text(screen, status, (station.x + 14, station.y + 44, station.w - 28, 21), DIM, 13)
        body = pygame.Rect(station.x + 12, station.y + 73, station.w - 24, station.h - 124)
        rail_w = min(350, max(240, round(body.w * .28)))
        main = pygame.Rect(body.x, body.y, body.w - rail_w - 12, body.h)
        rail = pygame.Rect(main.right + 12, body.y, rail_w, body.h)
        detail_h = min(254 if page == 2 else 216, rail.h - 92)
        details = pygame.Rect(rail.x, rail.y, rail.w, detail_h)
        contacts = pygame.Rect(rail.x, details.bottom + 8, rail.w, rail.bottom - details.bottom - 8)
        for rect in (main, details, contacts):
            pygame.draw.rect(screen, PANEL, rect)
            pygame.draw.rect(screen, GRID, rect, 1)
        with layout.clip_to(screen, main):
            if page < 2:
                _draw_waterfall(game, main, page)
            elif page == 2:
                _draw_demon(game, main)
            elif page == 3:
                _draw_tma(game, main)
            else:
                _draw_environment(game, main)
        with layout.clip_to(screen, details):
            _draw_details(game, details, page)
        _draw_contacts(game, contacts)
        footer = ("Bild auf/ab Seite | R Peilung | Links/Rechts Strahl | Enter Track/manuell | E Bathythermograph | U/V TAS-Tiefe",
                   "Auf/Ab Kontakt | J Ton | ,/. Pegel | D Band-Ton | I/O Gain | F Band | N Notch | Space Peak | A Ping | C Klasse | M Ziel")
        for i, line in enumerate(footer):
            _text(screen, line, (station.x + 14, station.bottom - 42 + i * 21, station.w - 28, 19), DIM, 13)

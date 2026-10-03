"""Geometry and hit testing of the sonar station: panel layout, plot
areas, click targets and hover tooltips.  Moved verbatim from
``sonar_view.py``, which re-exports every name.
"""

import numpy as np
import pygame

from src.core import config
from src.core.i18n import (
    display_value, localized, localize, message as structured_message)
from src.ui import layout
from src.ui import observations
from src.ui.sonar_data import (
    PAGES, DEMON_DISPLAY_MAX_HZ, _sonar_observer, message, _observed_bearing,
    _bearing_line, _history_for_page, _list_rows, _array_readout,
    _circular_broadband, _linear_lofar, _process_lofar_rows,
    _waterfall_controls, active_echoes, _selected_harmonic, _bearing_series)


def _panels(game, page):
    """Three columns (UI grid, stage 3): contact cards on the left, the
    page's main display in the middle, listening console and readouts on
    the right, each the full body height."""
    station = pygame.Rect(config.STATION_RECT)
    body = pygame.Rect(station.x + 10, station.y + 43,
                       station.w - 20, station.h - 68)
    gap = 10
    contacts_w = min(272, max(220, round(body.w * .215)))
    details_w = min(300, max(240, round(body.w * .24)))
    contacts = pygame.Rect(body.x, body.y, contacts_w, body.h)
    details = pygame.Rect(body.right - details_w, body.y, details_w, body.h)
    main = pygame.Rect(contacts.right + gap, body.y,
                       details.x - gap - contacts.right - gap, body.h)
    return main, details, contacts


def _waterfall_plot(panel, page):
    top = panel.y + (105 if page == 1 else 61)
    return pygame.Rect(panel.x + 57, top, panel.w - 83,
                       panel.bottom - 47 - top)


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
    contacts, contact_keys = _contact_key_rows(game, contacts)
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
                contacts=contacts, footer=footer, contact_keys=contact_keys)


# The selected contact's orders as key chips under the contact cards (full
# mouse control): classify, TMA, release to the OPZ, target and the towed
# arrays.  The submarine's sonar room has no OPZ and no towed arrays.
CONTACT_KEYS_FRIGATE = ((("C", "sonar.keys.classify"), ("T", "sonar.keys.tma")),
                        (("G", "sonar.keys.release"), ("M", "sonar.keys.target")),
                        (("Y", "sonar.keys.tas"), ("Shift+Y", "sonar.keys.vds")))
CONTACT_KEYS_BOAT = ((("C", "sonar.keys.classify"), ("T", "sonar.keys.tma")),
                     (("M", "sonar.keys.target"),))
CONTACT_KEY_ROW_H = 22
CONTACT_KEY_GAP = 2


def contact_key_specs(game):
    return (CONTACT_KEYS_BOAT if getattr(game, "local_side", None) == "uboot"
            else CONTACT_KEYS_FRIGATE)


def _contact_key_rows(game, contacts):
    """Split the contact column: the cards' panel above, chip rows below."""
    specs = contact_key_specs(game)
    height = len(specs) * (CONTACT_KEY_ROW_H + CONTACT_KEY_GAP)
    panel = pygame.Rect(contacts.x, contacts.y, contacts.w, contacts.h - height - 4)
    rows = []
    y = panel.bottom + 4 + CONTACT_KEY_GAP
    for row in specs:
        rows.append((pygame.Rect(contacts.x, y, contacts.w, CONTACT_KEY_ROW_H), row))
        y += CONTACT_KEY_ROW_H + CONTACT_KEY_GAP
    return panel, rows


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

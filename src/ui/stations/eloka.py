"""ELOKA station view: intercepts, signal traces and candidates (verbatim from
``stations_view``)."""


import pygame

from src.ui import theme

from src.core import config, status_tips
from src.core.i18n import localized, localize, raw_text
from src.core.station import Station
from src.sensors.esm import animated_signal_fingerprint, spectrum_band
from src.ui import layout, pointer, sferics


from src.ui.stations.common import (_shortcut_footer, _srect, _station_content_top,
                                    draw_station_page_tabs, message)


def _near_point(pos, point, radius):
    return ((pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2
            <= radius ** 2)


ELOKA_CARDS_W = 262
ELOKA_DETAILS_W = 320
ELOKA_CARD_H = 50
ELOKA_CARD_PITCH = 54


def eloka_regions(station_rect=None, page=0) -> dict[str, pygame.Rect]:
    """Shared full-station geometry for ELOKA drawing and hit testing.

    A wide station gets three columns: intercept cards on the left, the
    page's picture in the middle and (on the intercept page) the selected
    intercept on the right.  A narrow station keeps the single box.
    """
    station = pygame.Rect(station_rect or config.STATION_RECT)
    inner_x = station.x + 14
    inner_w = station.w - 28
    top = _station_content_top(station, 2)
    bottom = station.bottom - 34  # the key legend row sits below the box
    height = max(1, bottom - top)
    empty = pygame.Rect(0, 0, 0, 0)
    if station.w < 1000:
        return {
            "cards": empty,
            "picture": pygame.Rect(inner_x, top, inner_w, height) if page == 0 else empty,
            "details": empty,
            "evidence": pygame.Rect(inner_x, top, inner_w, height) if page == 1 else empty,
        }
    gap = 10
    cards = pygame.Rect(inner_x, top, ELOKA_CARDS_W, height)
    rest = pygame.Rect(cards.right + gap, top, inner_x + inner_w - cards.right - gap, height)
    details = pygame.Rect(rest.right - ELOKA_DETAILS_W, top, ELOKA_DETAILS_W, height)
    picture = pygame.Rect(rest.x, top, details.x - gap - rest.x, height)
    return {
        "cards": cards,
        "picture": picture if page == 0 else empty,
        "details": details if page == 0 else empty,
        "evidence": rest if page == 1 else empty,
    }


def short_key(track_key: str) -> str:
    """A card-sized intercept key: "E0000000000000012" -> "E12"."""
    head, digits = track_key[:1], track_key[1:]
    return head + str(int(digits)) if digits.isdigit() else track_key


def eloka_cards(game, station_rect=None, page=0) -> list:
    """(track, rect) for every intercept card the left column shows, scrolled
    so the selected intercept stays visible."""
    column = eloka_regions(station_rect, page)["cards"]
    if column.w <= 0 or game.damage.station_down("opz"):
        return []
    tracks = game.eloka_visible_tracks()
    capacity = max(1, (column.h - 36) // ELOKA_CARD_PITCH)
    selected = next((index for index, track in enumerate(tracks)
                     if track.track_key == game.eloka_selected_track_key), 0)
    start = max(0, min(selected - capacity // 2, max(0, len(tracks) - capacity)))
    return [(track, pygame.Rect(column.x + 6, column.y + 34 + index * ELOKA_CARD_PITCH,
                                column.w - 12, ELOKA_CARD_H))
            for index, track in enumerate(tracks[start:start + capacity])]


def _eloka_visible_tracks(game) -> tuple:
    tracks = game.eloka_visible_tracks()
    selected = next((index for index, track in enumerate(tracks)
                     if track.track_key == game.eloka_selected_track_key), 0)
    start = max(0, min(selected - 5, max(0, len(tracks) - 11)))
    return tracks[start:start + 11]


def _draw_eloka_signal(surface, rect, track, now: float, channel=None) -> None:
    """Draw normalized RF spectrum and modulation samples from observations."""
    rect = pygame.Rect(rect)
    if rect.w < 80 or rect.h < 70:
        return
    pygame.draw.rect(surface, theme.c("well"), rect)
    pygame.draw.rect(surface, config.COLOR_SONAR_RING, rect, 1)
    title_h = 24
    layout.blit_line(surface, "eloka.heading.signal_fingerprint",
                     (rect.x + 7, rect.y + 3, rect.w - 14, title_h),
                     config.COLOR_TEXT, size=16)
    graph = pygame.Rect(rect.x + 7, rect.y + title_h + 3,
                        rect.w - 14, rect.h - title_h - 9)
    split = graph.y + graph.h // 2
    for fraction in (.25, .5, .75):
        x = graph.x + round(graph.w * fraction)
        pygame.draw.line(surface, config.COLOR_GRID, (x, graph.y),
                         (x, graph.bottom), 1)
    pygame.draw.line(surface, theme.c("line_strong"), (graph.x, split),
                     (graph.right, split), 1)
    fingerprint = animated_signal_fingerprint(
        track, now,
        technique=None if channel is None else channel.technique,
        effectiveness=0.0 if channel is None else channel.effectiveness,
        samples=48, bins=40)
    status = (message("eloka.signal.memory", age=f"{track.age(now):.0f}")
              if fingerprint.memory_hold else localize("eloka.signal.live"))
    layout.blit_line(surface, status,
                     (rect.x + rect.w // 2, rect.y + 3,
                      rect.w // 2 - 7, title_h),
                     config.COLOR_TEXT_DIM if fingerprint.memory_hold
                     else config.COLOR_OK, size=14, align="right")
    def faded(color):
        scale = .35 + .65 * fingerprint.intensity
        return tuple(round(component * scale) for component in color)

    spectrum_h = max(8, split - graph.y - 4)
    spectrum_points = [(
        graph.x + round(index * (graph.w - 1)
                        / max(1, len(fingerprint.spectrum) - 1)),
        split - 3 - round(value * spectrum_h))
        for index, value in enumerate(fingerprint.spectrum)]
    if len(spectrum_points) > 1:
        pygame.draw.lines(surface, faded(config.COLOR_WARN), False,
                          spectrum_points, 2)
    wave_mid = split + max(4, (graph.bottom - split) // 2)
    wave_amp = max(3, (graph.bottom - split) // 2 - 4)
    wave_points = [(
        graph.x + round(index * (graph.w - 1)
                        / max(1, len(fingerprint.waveform) - 1)),
        wave_mid - round(value * wave_amp))
        for index, value in enumerate(fingerprint.waveform)]
    if len(wave_points) > 1:
        pygame.draw.lines(surface, faded(config.COLOR_OK), False, wave_points, 2)


def _eloka_list_w(picture: pygame.Rect) -> int:
    """The intercept list's width: the rest of a wide picture holds the rose."""
    return picture.w if picture.w < 700 else int(picture.w * .58)


_THREAT_COLORS = {"critical": "COLOR_DANGER", "high": "COLOR_DANGER",
                  "medium": "COLOR_WARN"}


def _eloka_lamp_rows(game) -> list:
    from src.ui import console
    return console.with_tips(_eloka_lamp_states(game), [
        status_tips.lazy(lambda: status_tips.eloka(game), name)
        for name in ("esm", "jammer", "auto", "tone")])


def _eloka_lamp_states(game) -> tuple:
    jamming = bool(getattr(game.ecm_jammer, "channels", ()))
    down = game.damage.station_down("opz")
    return (
        ("eloka.lamp.esm", "", "alarm" if down else "on"),
        # Jammer, automatic ECM and tone are switches (E, A, J).
        ("eloka.lamp.jammer", "", "caution" if jamming else "off", "E"),
        ("eloka.lamp.auto", "", "on" if game.ecm_jammer.auto_enabled else "off", "A"),
        ("eloka.lamp.tone", "", "on" if getattr(game, "eloka_audio_enabled", False) else "off",
         "J"))


def _draw_eloka_rose(game, rect, tracks, lamps=True) -> None:
    """North-up threat rose: one strobe per intercept, longer when fresher,
    coloured by the operator's threat reading; own course as a short line."""
    from src.ui import console
    surface = game.screen
    lamp_h = layout.line_pitch(14, 0) + 8
    if lamps:
        console.lamp_grid(surface, (rect.x, rect.bottom - 2 * lamp_h - 4, rect.w,
                                    2 * lamp_h + 4), _eloka_lamp_rows(game), 2, size=14)
    strobes = []
    for track in tracks:
        analysis = game.eloka_display_analysis(track)
        threat = "unknown" if analysis is None else analysis.threat_level
        color = getattr(config, _THREAT_COLORS.get(threat, "COLOR_OK"))
        quality = max(.2, min(1.0, float(track.display_quality(game.sim_t))))
        selected = track.track_key == game.eloka_selected_track_key
        strobes.append((track.bearing, config.COLOR_TEXT if selected else color,
                        3 if selected else 2, 0, 1 - .7 * quality))
    rose = (pygame.Rect(rect.x, rect.y, rect.w, rect.h - 2 * lamp_h - 16) if lamps
            else pygame.Rect(rect))
    console.bearing_rose(surface, rose, strobes, course=getattr(game.ship, "course", None),
                         title="eloka:rose")
    storm = game.world.thunderstorm()
    if storm > 0.0 and min(rose.w, rose.h) // 2 - 20 >= 30:
        sferics.draw_rose(surface, rose.center, min(rose.w, rose.h) // 2 - 20, storm, game._t)
        sferics.draw_label(surface, (rose.x, rose.bottom - 2, rose.w, 16), storm)


def eloka_track_at(game, pos, station_rect=None):
    """Return the displayed passive intercept at a canvas position."""
    if pos is None or game.damage.station_down("opz"):
        return None
    from src.core.commands import STATION_PAGES
    page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.ELOKA])
    regions = eloka_regions(station_rect, page=page)
    if regions["cards"].w > 0:
        return next((track for track, rect in eloka_cards(game, station_rect, page)
                     if rect.collidepoint(pos)), None)
    if not regions["picture"].collidepoint(pos):
        return None
    row_y = regions["picture"].y + layout.font(18).get_linesize() + 58
    row_height = 40
    tracks = _eloka_visible_tracks(game)
    for index, track in enumerate(tracks):
        if pygame.Rect(regions["picture"].x, row_y + index * row_height,
                       _eloka_list_w(regions["picture"]), 36).collidepoint(pos):
            return track
    return None


def _threat_color(game, track):
    analysis = game.eloka_display_analysis(track)
    threat = "unknown" if analysis is None else analysis.threat_level
    return getattr(config, _THREAT_COLORS.get(threat, "COLOR_OK"))


def _draw_eloka_cards(game, surface, column, page) -> None:
    """Left column: one card per intercept (threat stripe, key, bearing,
    frequency and band, quality and age); a click selects it."""
    layout.box(surface, column, "eloka.panel.intercepts")
    if game.damage.station_down("opz"):
        layout.blit_block(surface, "eloka.state.disabled", column.x + 12, column.y + 36,
                          column.w - 24, 48, color=config.COLOR_DANGER, size=16)
        return
    cards = eloka_cards(game, page=page)
    if not cards:
        layout.blit_block(surface, "eloka.state.empty", column.x + 12, column.y + 36,
                          column.w - 24, 48, color=config.COLOR_TEXT_DIM, size=15)
    for track, rect in cards:
        chosen = track.track_key == game.eloka_selected_track_key
        age = track.age(game.sim_t)
        fresh = age < game.esm_picture.stale_s / 2
        pygame.draw.rect(surface, config.COLOR_TAB_ACTIVE if chosen else theme.c("raised"),
                         rect, border_radius=4)
        pygame.draw.rect(surface, theme.c("focus") if chosen else theme.c("line"),
                         rect, 2 if chosen else 1, border_radius=4)
        pygame.draw.rect(surface, _threat_color(game, track),
                         (rect.x + 3, rect.y + 5, 3, rect.h - 10))
        text = config.COLOR_TEXT if fresh or chosen else config.COLOR_TEXT_DIM
        layout.blit_line(surface, raw_text(short_key(track.track_key)), (rect.x + 12, rect.y + 3,
                                                              rect.w - 96, 20),
                         text, size=15)
        layout.blit_line(surface, f"{track.bearing:05.1f}\u00b0",
                         (rect.right - 84, rect.y + 2, 76, 21), text, size=17,
                         align="right")
        layout.blit_line(surface, message(
            "eloka.card.signal",
            frequency=f"{track.frequency_hz / 1e9:.3f}",
            # The band letters only: "I-J / X-Ku band" -> "I-J".
            band=localize("eloka.band." + spectrum_band(track.frequency_hz).value)
            .split(" / ")[0],
            quality=f"{track.display_quality(game.sim_t):.0%}", age=f"{age:.0f}"),
            (rect.x + 12, rect.y + 26, rect.w - 20, 19), config.COLOR_TEXT_DIM, size=13)


def _draw_eloka_details(game, surface, column) -> None:
    """Right column of the intercept page: the selected intercept's signal,
    its reading and the ESM/ECM switches."""
    from src.ui import console
    box = layout.box(surface, column, "eloka.panel.selected")
    rx, ry, rw, rh = box
    lamp_h = layout.line_pitch(14, 0) + 8
    lamps_h = 2 * lamp_h + 4
    console.lamp_grid(surface, (rx, column.bottom - 8 - lamps_h, rw, lamps_h),
                      _eloka_lamp_rows(game), 2, size=14)
    selected = (None if game.damage.station_down("opz")
                else game.selected_eloka_track())
    if selected is None:
        layout.blit_block(surface, "eloka.state.no_selection", rx, ry, rw, 42,
                          color=config.COLOR_TEXT_DIM, size=15)
        return
    channel = next((item for item in game.ecm_jammer.channels
                    if item.track_key == selected.track_key), None)
    signal_h = 112
    _draw_eloka_signal(surface, (rx, ry, rw, signal_h), selected, game.sim_t, channel)
    analysis = game.eloka_display_analysis(selected)
    rows = (
        ("eloka.field.intercept", raw_text(short_key(selected.track_key))),
        ("eloka.field.bearing", message("eloka.value.bearing",
                                         bearing=f"{selected.bearing:05.1f}",
                                         error=f"{selected.bearing_uncertainty_deg:.1f}")),
        ("eloka.field.radar_type", localize(
            "eloka.radar_type." + (analysis.radar_type.value
                                   if analysis is not None and analysis.radar_type is not None
                                   else "unassessed"))),
        ("eloka.field.threat", localize(
            "eloka.threat." + (analysis.threat_level if analysis is not None
                               else "unknown"))),
        ("eloka.field.ecm", localize("eloka.value.ecm_off") if channel is None
         else localize("eloka.technique." + channel.technique)),
        ("eloka.field.annotation",
         game.eloka_annotation_name(selected.track_key) or localize("common.unknown")),
    )
    y = ry + signal_h + 10
    step = max(25, layout.font(15).get_linesize() + 4)
    # Labels as wide as the longest one needs, the values take the rest.
    label_w = min(rw // 2, max(layout.text_width(layout.font(14), localize(label))
                               for label, _value in rows) + 10)
    limit = column.bottom - 8 - lamps_h - 6
    for label, value in rows:
        if y + step > limit:
            break
        layout.status_line(surface, rx, y, rw, label, value, label_w=label_w, size=14)
        y += step
    # The best library candidates, as far as the column has room.
    y += 6
    if y + 3 * step > limit:
        return
    layout.blit_block(surface, "eloka.heading.candidates" if game.operator_assist()
                      else "eloka.heading.library", rx, y, rw, 2 * step - 4,
                      config.COLOR_TEXT, size=15)
    y += 2 * step
    for candidate in game.eloka_display_candidates(selected)[:3]:
        if y + step > limit:
            break
        name = game.eloka_emitter_name(candidate.emitter_key) or candidate.emitter_key
        layout.blit_line(surface, message(
            "eloka.line.candidate", emitter=name,
            score=f"{candidate.score:.0%}") if candidate.score is not None
            else raw_text(name), (rx, y, rw, 22), config.COLOR_TEXT_DIM, size=15)
        y += step


@localized
def draw_eloka_view(game, tr=None) -> None:
    """Render only the detached passive ESM picture and operator annotations."""
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    surface = game.screen
    pages = STATION_PAGES[Station.ELOKA]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    layout.panel(surface, _srect(), "station.eloka.title")
    draw_station_page_tabs(surface, station, pages, page, tr)
    regions = eloka_regions(page=page)
    if regions["cards"].w > 0:
        _draw_eloka_cards(game, surface, regions["cards"], page)
    if page == 0 and regions["cards"].w > 0:
        box = layout.box(surface, regions["picture"], "eloka.panel.picture")
        bx, by, bw, bh = box
        if not game.damage.station_down("opz"):
            layout.blit_line(surface, message(
                "eloka.filter.summary", status=localize(
                    "eloka.filter.status." + game.eloka_status_filter.lower()),
                threat=localize(
                    "eloka.filter.threat." + game.eloka_threat_filter.lower()),
                band=localize("eloka.filter.band." + game.eloka_band_filter.lower())),
                (bx, by, bw, 22), config.COLOR_TEXT_DIM, size=15)
            layout.blit_line(surface, message(
                "eloka.filter.count", visible=len(game.eloka_visible_tracks()),
                total=len(game.eloka_tracks())),
                (bx, by + 23, bw, 20), config.COLOR_TEXT_DIM, size=14)
        rose = pygame.Rect(bx, by + 50, bw, bh - 50)
        _draw_eloka_rose(game, rose, [] if game.damage.station_down("opz")
                         else game.eloka_visible_tracks(), lamps=False)
        _draw_eloka_details(game, surface, regions["details"])
    elif page == 0:
        box = layout.box(surface, regions["picture"], "eloka.panel.intercepts")
        bx, by, bw, _ = box
        list_w = _eloka_list_w(regions["picture"])
        if list_w < regions["picture"].w:
            rose = pygame.Rect(regions["picture"].x + list_w + 8, by,
                               regions["picture"].right - list_w - regions["picture"].x - 18,
                               box[3])
            pygame.draw.line(surface, config.COLOR_GRID, (rose.x - 4, by), (rose.x - 4, rose.bottom))
            _draw_eloka_rose(game, rose, [] if game.damage.station_down("opz")
                             else _eloka_visible_tracks(game))
            bw = list_w - 20
        if game.damage.station_down("opz"):
            layout.blit_block(surface, "eloka.state.disabled", bx, by, bw, 48,
                              color=config.COLOR_DANGER, size=18)
        else:
            row_h = max(42, layout.font(18).get_linesize() + 14)
            capacity = max(1, (box[3] - row_h - 76) // row_h)
            tracks = _eloka_visible_tracks(game)[:capacity]
            total = len(game.eloka_tracks())
            visible = len(game.eloka_visible_tracks())
            layout.blit_line(surface, message(
                "eloka.filter.summary", status=localize(
                    "eloka.filter.status." + game.eloka_status_filter.lower()),
                threat=localize(
                    "eloka.filter.threat." + game.eloka_threat_filter.lower()),
                band=localize("eloka.filter.band." + game.eloka_band_filter.lower())),
                (bx, by, bw, 22), config.COLOR_TEXT_DIM, size=15)
            by += 23
            layout.blit_line(surface, message(
                "eloka.filter.count", visible=visible, total=total),
                (bx, by, bw, 20), config.COLOR_TEXT_DIM, size=14)
            by += 23
            if not tracks:
                layout.blit_block(surface, "eloka.state.empty", bx, by, bw, 48,
                                  color=config.COLOR_TEXT_DIM, size=17)
            for track in tracks:
                selected = track.track_key == game.eloka_selected_track_key
                if selected:
                    pygame.draw.rect(surface, config.COLOR_SELECT_BG,
                                     (bx - 5, by - 2, bw + 10, row_h - 4))
                    pygame.draw.rect(surface, config.COLOR_WARN,
                                     (bx - 5, by - 2, 3, row_h - 4))
                age = track.age(game.sim_t)
                layout.blit_line(
                    surface,
                    message("eloka.line.intercept",
                            prefix=">" if selected else " ",
                            track=track.track_key,
                            bearing=f"{track.bearing:05.1f}",
                            frequency=f"{track.frequency_hz / 1e9:.3f}",
                            quality=f"{track.display_quality(game.sim_t):.0%}",
                            age=f"{age:.0f}"),
                    (bx, by, bw, row_h - 8),
                    config.COLOR_WARN if selected else
                    config.COLOR_TEXT if age < game.esm_picture.stale_s / 2
                    else config.COLOR_TEXT_DIM,
                    size=18)
                by += row_h
    else:
        box = layout.box(surface, regions["evidence"], "eloka.panel.evidence")
        rx, ry, rw, rh = box
        selected = (None if game.damage.station_down("opz")
                    else game.selected_eloka_track())
        if selected is None:
            layout.blit_block(surface, "eloka.state.no_selection", rx, ry, rw, 42,
                              color=config.COLOR_TEXT_DIM, size=18)
        else:
            modulation = localize("eloka.modulation." + selected.modulation_code)
            prf = f"{selected.prf_hz:.0f} Hz" if selected.prf_hz is not None else "--"
            analysis = game.eloka_display_analysis(selected)
            channel = next((item for item in game.ecm_jammer.channels
                            if item.track_key == selected.track_key), None)
            values = (
                ("eloka.field.intercept", raw_text(short_key(selected.track_key))),
                ("eloka.field.release", localize(
                    "eloka.release.active" if game.eloka_annotation(selected.track_key)
                    else "eloka.release.private")),
                ("eloka.field.bearing", message("eloka.value.bearing",
                                                 bearing=f"{selected.bearing:05.1f}",
                                                 error=f"{selected.bearing_uncertainty_deg:.1f}")),
                ("eloka.field.frequency", localize(message(
                    "eloka.value.frequency",
                    frequency=f"{selected.frequency_hz / 1e9:.3f}"))
                 + " / " + localize("eloka.band." + spectrum_band(
                     selected.frequency_hz).value)),
                ("eloka.field.prf", prf),
                ("eloka.field.modulation", modulation),
                ("eloka.field.quality_age", message(
                    "eloka.value.quality_age",
                    quality=f"{selected.display_quality(game.sim_t):.0%}",
                    age=f"{selected.age(game.sim_t):.1f}")),
                ("eloka.field.signal", message(
                    "eloka.value.signal", level=f"{selected.signal_db:.0f}",
                    range=(f"{estimate:.0f}" if (estimate := game.eloka_display_range(
                        selected)) is not None else "--"),
                    scan=(f"{selected.revisit_s:.1f}" if selected.revisit_s > 0.0
                          else "--"))),
                ("eloka.field.radar_type", localize(
                    "eloka.radar_type." + (analysis.radar_type.value
                    if analysis is not None and analysis.radar_type is not None
                    else "unassessed"))),
                ("eloka.field.threat", localize(
                    "eloka.threat." + (analysis.threat_level
                    if analysis is not None else "unknown"))),
                ("eloka.field.synthetic", localize(
                    "eloka.value.synthetic" if selected.synthetic_assumption
                    else "eloka.value.observed")),
                ("eloka.field.ecm", localize("eloka.value.ecm_off") if channel is None
                 else message("eloka.value.ecm_detail",
                              technique=localize("eloka.technique." + channel.technique),
                              effectiveness=f"{channel.effectiveness:.0%}",
                              power=f"{channel.power_draw:.0%}",
                              lock=localize("ui.on" if channel.is_locked_on else "ui.off"))),
                ("eloka.field.annotation",
                 game.eloka_annotation_name(selected.track_key) or localize("common.unknown")),
            )
            # Details and analysis used to be stacked into one column.  With
            # radar type/threat/ECM added that exceeded the 510 px uConsole
            # station height and painted over the footer.  Keep both columns
            # inside one explicitly clipped content area instead.
            content = pygame.Rect(rx, ry, rw, max(1, box[1] + box[3] - ry - 8))
            gap = 14
            details_w = max(270, int(rw * .58))
            analysis_x = rx + details_w + gap
            analysis_w = max(1, rw - details_w - gap)
            detail_step = max(27, layout.font(16).get_linesize() + 5)
            with layout.clip_to(surface, content):
                detail_y = ry
                for label, value in values:
                    if detail_y + detail_step > content.bottom:
                        break
                    layout.status_line(surface, rx, detail_y, details_w,
                                       label, value, label_w=138, size=16)
                    detail_y += detail_step

                analysis_y = ry
                signal_h = min(128, max(96, content.h // 3))
                _draw_eloka_signal(
                    surface, (analysis_x, analysis_y, analysis_w, signal_h),
                    selected, game.sim_t, channel)
                analysis_y += signal_h + 10
                assist = game.operator_assist()
                # The heading may wrap beside the cards column (large text).
                heading = "eloka.heading.candidates" if assist else "eloka.heading.library"
                heading_face, heading_lines = layout.fit_text(
                    localize(heading), 17, analysis_w, 52, layout.MIN_OPERATIONAL_FONT)
                heading_h = len(heading_lines) * layout.line_pitch(17, 0) + 4
                layout.blit_block(surface, heading, analysis_x, analysis_y, analysis_w,
                                  heading_h, config.COLOR_TEXT, size=17)
                analysis_y += heading_h + 4
                shown = game.eloka_display_candidates(selected)
                for candidate in shown[:3]:
                    name = (game.eloka_emitter_name(candidate.emitter_key)
                            or candidate.emitter_key)
                    layout.blit_line(surface, message(
                        "eloka.line.candidate", emitter=name,
                        score=f"{candidate.score:.0%}") if candidate.score is not None
                        else raw_text(name),
                        (analysis_x, analysis_y, analysis_w, 25),
                        config.COLOR_TEXT_DIM, size=16)
                    analysis_y += 28
                if not assist:
                    hint = message("eloka.library_hint", count=len(shown))
                    _face, hint_lines = layout.fit_text(
                        localize(hint), 16, analysis_w, 50, layout.MIN_OPERATIONAL_FONT)
                    hint_h = len(hint_lines) * layout.line_pitch(16, 0) + 4
                    layout.blit_block(surface, hint, analysis_x, analysis_y, analysis_w,
                                      hint_h, config.COLOR_TEXT_DIM, size=16)
                    pointer.add_token_keys((analysis_x, analysis_y, analysis_w, hint_h), hint,
                                           16, (("C", "C"),),
                                           min_size=layout.MIN_OPERATIONAL_FONT, screen=surface)
                    analysis_y += hint_h + 4
                analysis_y += 8
                layout.blit_line(surface, "eloka.heading.correlations",
                                 (analysis_x, analysis_y, analysis_w, 24),
                                 config.COLOR_TEXT, size=17)
                analysis_y += 28
                correlations = game.eloka_correlations(selected)
                if not correlations:
                    layout.blit_line(surface, "eloka.correlation.none",
                                     (analysis_x, analysis_y, analysis_w, 25),
                                     config.COLOR_TEXT_DIM, size=16)
                else:
                    for correlation in correlations[:2]:
                        layout.blit_line(surface, message(
                            "eloka.line.correlation", source=correlation.source,
                            track=correlation.track_id,
                            score=f"{correlation.score:.0%}",
                            ambiguity=localize("eloka.correlation.ambiguous")
                            if correlation.ambiguous else ""),
                            (analysis_x, analysis_y, analysis_w, 25),
                            config.COLOR_OK, size=16)
                        analysis_y += 28
    _shortcut_footer(surface, (station.x + 14, station.bottom - 26, station.w - 28, 20), (
        ("↑/↓", "eloka.footer.select"),
        ("E", "eloka.footer.jam"),
        ("A", "eloka.footer.ecm_auto"),
        ("J", message("eloka.footer.audio", audio=localize(
            "ui.on" if getattr(game, "eloka_audio_enabled", True) else "ui.off"))),
    ))

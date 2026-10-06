"""Read-only tactical unit analyzer for the detached contact catalog."""

from __future__ import annotations

import webbrowser
from collections import OrderedDict
from io import BytesIO
from typing import Mapping

import pygame

from src.core.i18n import message, raw_text, translation_scope
from src.data.catalog import CATALOG
from src.data.contact_analysis import (ASSET_ROUTE_PREFIX,
                                       load_contact_analysis_assets,
                                       project_contact_catalog)
from src.ui import editor_widgets as widgets
from src.ui import layout, unit_models


MAX_FILTER_CHARS = 48
SURFACE_CACHE_SIZE = 4
_ASSET_ORDER = ("acoustic_cruise", "acoustic_high", "radar")
# The turning 3D model is the first page of every profile; it is drawn,
# not a packaged image.
MODEL_KIND = "model"
_RESOURCE_KINDS = {"subs.json": "sub", "warships.json": "surface",
                   "civilians.json": "surface", "aircraft.json": "aircraft",
                   "animals.json": "animal", "torpedoes.json": "torpedo",
                   "decoys.json": "decoy"}


def _wiki_url_for(key: str, cat=CATALOG) -> str | None:
    """Look up an optional Wikipedia link directly from the in-process
    catalog - never through project_contact_catalog()'s served projection,
    which is deliberately kept URL-free for the web commander API."""
    for registry in (cat.subs, cat.surfaces, cat.aircraft):
        profile = registry.get(key)
        if profile is not None:
            return getattr(profile, "wiki_url", None)
    return None


class ContactAnalyzer:
    """Bounded catalog browser with no game-state or observation dependency."""

    mode = "browser"

    def __init__(self, tr=widgets.IDENTITY_TR, *, projection=None,
                 packaged_assets: Mapping[str, tuple[str, bytes]] | None = None,
                 on_play_sample=None, on_stop_sample=None, preview_active=None,
                 on_assign=None, assign_label=None, current_assignment=None,
                 fits: Mapping[str, float] | None = None):
        self.tr = tr
        # In-game with line marks: fit of each class to the operator's marks
        # (sonar class library); the list is shown best fit first.
        self.fits = dict(fits or {})
        # In-game only: assign the selected profile to the operator's sonar
        # contact (an annotation, like a manual classification).
        self.on_assign = on_assign
        self.assign_label = assign_label
        self.current_assignment = current_assignment
        self.assign_notice = None
        self.on_play_sample = on_play_sample
        self.on_stop_sample = on_stop_sample
        self.preview_active = preview_active
        self._playing_sample = None
        detached = project_contact_catalog() if projection is None else projection
        self.profiles = list(detached["profiles"])
        if self.fits:
            self.profiles.sort(key=lambda profile: -self.fits.get(profile["key"], -1.0))
        assets = load_contact_analysis_assets() if packaged_assets is None else packaged_assets
        self._asset_bytes = {
            route: payload for route, (mime, payload) in assets.items()
            if route.startswith(ASSET_ROUTE_PREFIX) and mime == "image/png"
        }
        self.surface_cache: OrderedDict[str, pygame.Surface] = OrderedDict()
        self.filter = widgets.FilterField(MAX_FILTER_CHARS)
        self.filtered = list(range(len(self.profiles)))
        self.listbox = widgets.ListBox(self._list_labels())
        self.detail_scroll = 0
        self.focus = "list"
        self.asset_index = 0
        self._key_text = ""
        self._rects: dict[str, pygame.Rect] = {}
        self._detail_visible = 1
        self.model_view = unit_models.ModelView()
        self._model_classes = unit_models.catalog_model_classes(CATALOG)
        self._prepare_selected_image()

    @property
    def selected_profile(self):
        if not self.filtered:
            return None
        return self.profiles[self.filtered[self.listbox.selected]]

    def _list_labels(self):
        return [self._fit_prefix(self.profiles[index]["key"])
                + f"{self.profiles[index]['name']} [{self.profiles[index]['key']}]"
                for index in self.filtered]

    def _fit_prefix(self, key: str) -> str:
        if not self.fits:
            return ""
        fit = self.fits.get(key)
        return "  --  " if fit is None else f"{fit:4.0%}  "

    def _set_filter(self, value: str) -> None:
        self.filter.set(value)
        self.filtered = [
            index for index, profile in enumerate(self.profiles)
            if self.filter.matches(profile["key"], profile["name"],
                                   profile["resource"])
        ]
        self.listbox.selected = 0
        self.listbox.scroll = 0
        self.listbox.set_items(self._list_labels())
        self._stop_sample()
        self.detail_scroll = 0
        self.asset_index = 0
        self._prepare_selected_image()

    def _asset_kinds(self):
        profile = self.selected_profile
        if profile is None:
            return []
        return [MODEL_KIND] + [kind for kind in _ASSET_ORDER if kind in profile["assets"]]

    def model_class(self, profile) -> str:
        """3D model of an analyzer profile: the type's own variant, else the
        class (catalog key, else resource)."""
        known = self._model_classes.get(profile["key"])
        if known is None:
            known = unit_models.model_class(_RESOURCE_KINDS.get(profile["resource"], ""),
                                            profile["key"])
        return unit_models.model_key(profile["key"], known)

    def _decode_surface(self, route: str) -> pygame.Surface | None:
        cached = self.surface_cache.pop(route, None)
        if cached is not None:
            self.surface_cache[route] = cached
            return cached
        payload = self._asset_bytes.get(route)
        if payload is None:
            return None
        surface = pygame.image.load(BytesIO(payload), route.removeprefix(ASSET_ROUTE_PREFIX))
        self.surface_cache[route] = surface
        while len(self.surface_cache) > SURFACE_CACHE_SIZE:
            self.surface_cache.popitem(last=False)
        return surface

    def _prepare_selected_image(self) -> None:
        kinds = self._asset_kinds()
        if not kinds:
            self.asset_index = 0
            return
        self.asset_index %= len(kinds)
        if kinds[self.asset_index] == MODEL_KIND:
            return
        profile = self.selected_profile
        self._decode_surface(profile["assets"][kinds[self.asset_index]])

    def _selection_changed(self) -> None:
        self._stop_sample()
        self.detail_scroll = 0
        self.asset_index = 0
        self._prepare_selected_image()

    def _current_sample(self):
        """Aktuelle Hörprobe (Einheit, Modus) oder None ohne verfügbares Asset."""
        profile = self.selected_profile
        if profile is None:
            return None
        kinds = self._asset_kinds()
        if not kinds:
            return None
        kind = kinds[self.asset_index]
        if kind == MODEL_KIND:
            # The model page plays the first recording the profile has.
            if len(kinds) < 2:
                return None
            kind = kinds[1]
        return (profile["key"], kind)

    def _sample_available(self) -> bool:
        return (self._current_sample() is not None
                and self.on_play_sample is not None)

    def _stop_sample(self) -> None:
        if self._playing_sample is None:
            return
        self._playing_sample = None
        if self.on_stop_sample is not None:
            self.on_stop_sample()

    def _play_sample(self) -> bool:
        """Toggle: startet die gelesene Hörprobe (Endlos-Loop) oder stoppt sie."""
        sample = self._current_sample()
        if sample is None or self.on_play_sample is None:
            return False
        if self._playing_sample == sample:
            self._stop_sample()
            return True
        profile = self.selected_profile
        self.on_play_sample(profile["key"], sample[1], profile["machine"])
        self._playing_sample = sample
        return True

    def _open_wiki(self) -> bool:
        profile = self.selected_profile
        if profile is None:
            return False
        url = _wiki_url_for(profile["key"])
        if not url:
            return False
        webbrowser.open(url)
        return True

    def _shown(self, value) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return self.tr("common.yes" if value else "common.no")
        if isinstance(value, float):
            return f"{value:g}"
        if isinstance(value, (list, tuple)):
            return ", ".join(self._shown(item) for item in value) or "-"
        return str(value)

    def _detail_lines(self):
        profile = self.selected_profile
        if profile is None:
            return []
        reference, machine = profile["reference"], profile["machine"]
        rows = [
            ("analyzer.key", profile["key"]),
            ("analyzer.resource", profile["resource"]),
            ("analyzer.hull", reference["hull_type"]),
            ("analyzer.length", reference["length_m"]),
            ("analyzer.cruise_speed", machine["cruise_speed_kn"]),
            ("analyzer.maximum_speed", machine["maximum_speed_kn"]),
            ("analyzer.quiet_speed", machine["quiet_speed_kn"]),
            ("analyzer.propulsion", machine["propulsion_codes"]),
            ("analyzer.propulsor", machine["propulsor_type"]),
            ("analyzer.motor_rpm", machine["motor_rpm"]),
            ("analyzer.shaft_rpm", machine["shaft_rpm"]),
            ("analyzer.blades", machine["blade_count"]),
            ("analyzer.cruise_lines", len(machine["cruise_lines"])),
            ("analyzer.high_lines", len(machine["high_speed_lines"])),
        ]
        for kind in ("sensors", "emitters", "weapons", "launchers",
                     "magazines", "countermeasures"):
            rows.append((f"analyzer.{kind}", len(profile["components"][kind])))
        for index, sensor in enumerate(profile["components"]["sensors"], 1):
            rows.extend((
                ("analyzer.sensor", index),
                ("analyzer.domain", sensor["domain"]),
                ("analyzer.modes", sensor["modes"]),
                ("analyzer.emits", sensor["emits"]),
                ("analyzer.synthetic_range", sensor["synthetic_range_nm"]),
                ("analyzer.sensitivity", sensor["sensitivity_db"]),
                ("analyzer.cadence", sensor["cadence_s"]),
                ("analyzer.bearing_uncertainty",
                 sensor["bearing_uncertainty_deg"]),
                ("analyzer.range_uncertainty", sensor["range_uncertainty_nm"]),
                ("analyzer.depth_uncertainty", sensor["depth_uncertainty_m"]),
            ))
        for index, emitter in enumerate(profile["components"]["emitters"], 1):
            rows.extend((
                ("analyzer.emitter", index),
                ("analyzer.domain", emitter["domain"]),
                ("analyzer.frequency_band", emitter["frequency_band_hz"]),
                ("analyzer.prf_band", emitter["prf_band_hz"]),
                ("analyzer.modulation", emitter["modulation_codes"]),
            ))
        lines = []
        for label, value in rows:
            shown = self._shown(value)
            try:
                line = self.tr("analyzer.value", label=self.tr(label), value=shown)
            except TypeError:
                line = f"{self.tr(label)}: {shown}"
            lines.append(line)
        return lines

    def _scroll_detail(self, amount: int) -> bool:
        maximum = max(0, len(self._detail_lines()) - self._detail_visible)
        before = self.detail_scroll
        self.detail_scroll = max(0, min(maximum, self.detail_scroll + amount))
        return before != self.detail_scroll

    def _assign(self, clear: bool) -> None:
        """Enter assigns the selected profile to the contact, Shift+Enter clears."""
        profile = self.selected_profile
        if clear or profile is not None:
            result = self.on_assign(None if clear else profile["key"])
            self.assign_notice = ("analyzer.assign.cleared" if clear and result is True
                                  else "analyzer.assign.done" if result is True
                                  else "analyzer.assign.failed")

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if not (x or y):
                return False
            key = pygame.K_UP if y > 0 else pygame.K_DOWN if y < 0 else \
                pygame.K_LEFT if x < 0 else pygame.K_RIGHT
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="")

        before = self.listbox.selected
        list_rect = self._rects.get("list", pygame.Rect(28, 140, 370, 500))
        detail_rect = self._rects.get("detail", pygame.Rect(756, 130, 476, 490))
        if event.type == pygame.KEYDOWN:
            if (event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                    and self.on_assign is not None):
                self._assign(bool(getattr(event, "mod", 0) & pygame.KMOD_SHIFT))
                return True
            if event.key == pygame.K_TAB:
                self.focus = "detail" if self.focus == "list" else "list"
                return True
            if event.key == pygame.K_SPACE:
                if self._play_sample():
                    # Schluecke das zugehoerige TEXTINPUT, damit kein
                    # Leerzeichen in den Suchfilter gelangt.
                    self._key_text = " "
                    return True
                return False
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                kinds = self._asset_kinds()
                if kinds:
                    self.asset_index = (self.asset_index + (-1 if event.key == pygame.K_LEFT else 1)) % len(kinds)
                    self._stop_sample()
                    self._prepare_selected_image()
                return True
            if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP,
                             pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                if self.focus == "detail":
                    amount = {
                        pygame.K_UP: -1, pygame.K_DOWN: 1,
                        pygame.K_PAGEUP: -self._detail_visible,
                        pygame.K_PAGEDOWN: self._detail_visible,
                        pygame.K_HOME: -len(self._detail_lines()),
                        pygame.K_END: len(self._detail_lines()),
                    }[event.key]
                    return self._scroll_detail(amount)
                changed = self.listbox.handle_event(event, list_rect,
                                                     row_height=self._row_height())
                if self.listbox.selected != before:
                    self._selection_changed()
                return changed
            if self.filter.handle_event(event):
                self._set_filter(self.filter.text)
                return True
        if event.type == pygame.TEXTINPUT:
            if getattr(event, "text", "") == self._key_text:
                self._key_text = ""
                return True
            if self.filter.handle_event(event):
                self._set_filter(self.filter.text)
                return True
        position = getattr(event, "pos", None)
        if event.type == pygame.MOUSEWHEEL:
            if position is not None and detail_rect.collidepoint(position):
                self.focus = "detail"
                return self._scroll_detail(-event.y * 3)
            self.focus = "list"
            changed = self.listbox.handle_event(event, list_rect,
                                                 row_height=self._row_height())
            if self.listbox.selected != before:
                self._selection_changed()
            return changed
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and position:
            if self.on_assign is not None:
                # The assign and clear buttons, as Enter and Shift+Enter.
                for name, clear in (("assign", False), ("assign_clear", True)):
                    rect = self._rects.get(name)
                    if rect is not None and rect.collidepoint(position):
                        self._assign(clear)
                        return True
            audio_rect = self._rects.get("audio_sample")
            if audio_rect is not None and audio_rect.collidepoint(position):
                return self._play_sample()
            wiki_rect = self._rects.get("open_wiki")
            if wiki_rect is not None and wiki_rect.collidepoint(position):
                return self._open_wiki()
            for index, tab in enumerate(self._rects.get("asset_tabs", ())):
                if tab.collidepoint(position):
                    self.asset_index = index
                    self._stop_sample()
                    self._prepare_selected_image()
                    return True
            if detail_rect.collidepoint(position):
                self.focus = "detail"
                return True
            if list_rect.collidepoint(position):
                self.focus = "list"
                changed = self.listbox.handle_event(event, list_rect,
                                                     row_height=self._row_height())
                if self.listbox.selected != before:
                    self._selection_changed()
                return changed
        return False

    @staticmethod
    def _row_height() -> int:
        return 34 if layout.text_scale() > 1.0 else 28

    def draw(self, surface: pygame.Surface) -> None:
        with translation_scope(None):
            self._draw(surface)

    def _draw(self, surface: pygame.Surface) -> None:
        bounds = surface.get_rect()
        surface.fill(widgets.PALETTE.background)
        widgets.draw_text(surface, self.tr("analyzer.title"),
                          (20, 15, bounds.width - 40, 42), size=24, bold=True)
        wiki_rect = pygame.Rect(bounds.width - 614, 18, 84, 34)
        wiki_url = (_wiki_url_for(self.selected_profile["key"])
                   if self.selected_profile is not None else None)
        if wiki_url:
            self._rects["open_wiki"] = wiki_rect
            pygame.draw.rect(surface, widgets.PALETTE.raised, wiki_rect)
            pygame.draw.rect(surface, widgets.PALETTE.focus, wiki_rect, 1)
            widgets.draw_text(surface, self.tr("analyzer.open_wiki"), wiki_rect,
                              color=widgets.PALETTE.text, size=12, align="center")
        else:
            self._rects["open_wiki"] = None
        audio_rect = pygame.Rect(bounds.width - 522, 18, 84, 34)
        playing = bool(self.preview_active()) if callable(self.preview_active) else False
        if self._sample_available():
            self._rects["audio_sample"] = audio_rect
            pygame.draw.rect(surface, widgets.PALETTE.focus if playing
                             else widgets.PALETTE.raised, audio_rect)
            pygame.draw.rect(surface, widgets.PALETTE.text if playing
                             else widgets.PALETTE.focus, audio_rect, 1)
            widgets.draw_text(surface, self.tr("analyzer.audio_sample"),
                              audio_rect,
                              color=(widgets.PALETTE.focus if playing
                                     else widgets.PALETTE.text),
                              size=12, align="center")
        else:
            self._rects["audio_sample"] = None
            widgets.draw_text(surface, self.tr("analyzer.audio_sample"),
                              audio_rect, color=widgets.PALETTE.dim,
                              size=12, align="center")
        widgets.draw_text(surface, self.tr("analyzer.read_only"),
                          (bounds.width - 430, 18, 370, 34), color=widgets.PALETTE.focus,
                          size=13, bold=True, align="right")
        # The close box (F8 / Esc by mouse); the game takes its click.
        from src.ui import game_menu
        self.close_rect = game_menu.draw_close_box(surface, (0, 12, bounds.width - 4, 40))
        footer = pygame.Rect(0, bounds.height - 42, bounds.width, 42)
        # In-game assignment adds one hint line above the footer.
        assign_h = 28 if self.on_assign is not None else 0
        content = pygame.Rect(20, 66, bounds.width - 40, footer.y - 76 - assign_h)
        left = pygame.Rect(content.x, content.y, 390, content.height)
        left_inner = widgets.panel(surface, left, "analyzer.contacts_by_fit" if self.fits
                                   else "analyzer.contacts", tr=self.tr)
        filter_rect = pygame.Rect(left_inner.x, left_inner.y, left_inner.width, 34)
        self.filter.draw(surface, filter_rect, placeholder="analyzer.filter", tr=self.tr)
        list_rect = pygame.Rect(left_inner.x, filter_rect.bottom + 8, left_inner.width,
                                max(1, left_inner.bottom - filter_rect.bottom - 8))
        self._rects["list"] = list_rect
        self.listbox.draw(surface, list_rect, row_height=self._row_height())

        right = pygame.Rect(left.right + 12, content.y, content.right - left.right - 12,
                            content.height)
        inner = widgets.panel(surface, right, "analyzer.details", tr=self.tr)
        profile = self.selected_profile
        if profile is None:
            widgets.draw_text(surface, self.tr("analyzer.no_results"), inner,
                              color=widgets.PALETTE.dim, align="center")
        else:
            widgets.draw_text(surface, raw_text(profile["name"]),
                              (inner.x, inner.y, inner.width, 30), size=20, bold=True)
            image_box = pygame.Rect(inner.x, inner.y + 38, 324, 460)
            pygame.draw.rect(surface, widgets.PALETTE.background, image_box)
            pygame.draw.rect(surface, widgets.PALETTE.border, image_box, 1)
            kinds = self._asset_kinds()
            if kinds:
                kind = kinds[self.asset_index]
                if kind == MODEL_KIND:
                    model_rect = pygame.Rect(image_box.x + 2, image_box.y + 2,
                                             image_box.width - 4, 250)
                    self._rects["model"] = model_rect
                    self.model_view.draw(surface, model_rect, self.model_class(profile),
                                         background=widgets.PALETTE.background)
                    legend_y = model_rect.bottom + 6
                else:
                    route = profile["assets"][kind]
                    image = self.surface_cache.get(route)
                    if image is not None:
                        image_rect = image.get_rect(midtop=(image_box.centerx,
                                                            image_box.y + 4))
                        surface.blit(image, image_rect)
                    legend_y = image_box.y + 187
                legend_h = (image_box.bottom - 30 - legend_y) // 2
                spectrum_legend = pygame.Rect(image_box.x + 6, legend_y,
                                               image_box.width - 12, legend_h)
                hypothesis_legend = pygame.Rect(image_box.x + 6,
                                                 spectrum_legend.bottom,
                                                 image_box.width - 12,
                                                 image_box.bottom - 30 - spectrum_legend.bottom)
                self._rects["spectrum_legend"] = spectrum_legend
                self._rects["hypothesis_legend"] = hypothesis_legend
                if kind == MODEL_KIND:
                    top_key, bottom_key = ("analyzer.model_legend",
                                           "analyzer.model_scale_legend")
                elif kind == "radar":
                    top_key, bottom_key = ("analyzer.radar_spectrum_legend",
                                           "analyzer.radar_prf_legend")
                else:
                    top_key, bottom_key = ("analyzer.spectrum_legend",
                                           "analyzer.hypothesis_legend")
                layout.blit_block(surface, self.tr(top_key),
                                  *spectrum_legend, color=widgets.PALETTE.dim,
                                  size=16, min_size=16)
                layout.blit_block(surface, self.tr(bottom_key),
                                  *hypothesis_legend, color=widgets.PALETTE.dim,
                                  size=16, min_size=16)
                # The model tab is a narrow "3D"; the images share the rest.
                model_w = 44 if len(kinds) > 1 else image_box.width
                image_w = max(1, (image_box.width - model_w) // max(1, len(kinds) - 1))
                tabs = []
                x = image_box.x
                for index, asset_kind in enumerate(kinds):
                    width = model_w if asset_kind == MODEL_KIND else image_w
                    tab = pygame.Rect(x, image_box.bottom - 30, width, 30)
                    x += width
                    tabs.append(tab)
                    if index == self.asset_index:
                        pygame.draw.rect(surface, widgets.PALETTE.raised, tab)
                    label = ("analyzer.model_tab" if asset_kind == MODEL_KIND
                             else "analyzer." + asset_kind)
                    widgets.draw_text(surface, self.tr(label), tab,
                                      color=(widgets.PALETTE.focus if index == self.asset_index
                                             else widgets.PALETTE.dim), size=12, align="center")
                self._rects["asset_tabs"] = tabs
            else:
                self._rects["asset_tabs"] = []
                widgets.draw_text(surface, self.tr("analyzer.no_image"), image_box,
                                  color=widgets.PALETTE.dim, align="center")

            detail_rect = pygame.Rect(image_box.right + 14, inner.y + 38,
                                      max(1, inner.right - image_box.right - 14),
                                      inner.bottom - inner.y - 38)
            self._rects["detail"] = detail_rect
            line_height = 29 if layout.text_scale() > 1.0 else 24
            self._detail_visible = max(1, detail_rect.height // line_height)
            lines = self._detail_lines()
            self.detail_scroll = min(self.detail_scroll,
                                     max(0, len(lines) - self._detail_visible))
            pygame.draw.rect(surface, widgets.PALETTE.background, detail_rect)
            pygame.draw.rect(surface, widgets.PALETTE.focus if self.focus == "detail"
                             else widgets.PALETTE.border, detail_rect, 1)
            with widgets.clipped(surface, detail_rect.inflate(-6, -4)):
                for row, line in enumerate(lines[self.detail_scroll:
                                                 self.detail_scroll + self._detail_visible]):
                    widgets.draw_text(surface, raw_text(line),
                                      (detail_rect.x + 7, detail_rect.y + 3 + row * line_height,
                                       detail_rect.width - 14, line_height), size=13)
        if self.on_assign is not None:
            current = self.current_assignment() if self.current_assignment else None
            # Two buttons do what Enter and Shift+Enter do.
            assign = pygame.Rect(20, footer.y - 28, 300, 24)
            clear = pygame.Rect(assign.right + 10, assign.y, 220, 24)
            with translation_scope(self.tr):
                layout.key_button(surface, assign, "Enter",
                                  message("analyzer.assign.button",
                                          contact=raw_text(self.assign_label or "--")), size=14)
                layout.key_button(surface, clear, "Shift+Enter", "analyzer.assign.clear",
                                  size=14)
            self._rects["assign"], self._rects["assign_clear"] = assign, clear
            line = raw_text(self.tr("analyzer.assign.current",
                                    current=current or self.tr("common.unknown")))
            widgets.draw_text(surface, line, (clear.right + 14, footer.y - 26, 400, 22),
                              size=14)
            if self.assign_notice:
                widgets.draw_text(surface, self.assign_notice,
                                  (bounds.width - 420, footer.y - 26, 400, 22), size=14)
        widgets.draw_footer(surface, footer,
                            ("analyzer.filter_hint", "analyzer.select_hint",
                             "analyzer.image_hint", "analyzer.audio_hint",
                             "analyzer.scroll_hint", "analyzer.exit_hint"), tr=self.tr)

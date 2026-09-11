"""Read-only tactical unit analyzer for the detached contact catalog."""

from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
from typing import Mapping

import pygame

from src.core.i18n import raw_text, translation_scope
from src.data.contact_analysis import (ASSET_ROUTE_PREFIX,
                                       load_contact_analysis_assets,
                                       project_contact_catalog)
from src.ui import editor_widgets as widgets
from src.ui import layout


MAX_FILTER_CHARS = 48
SURFACE_CACHE_SIZE = 4
_ASSET_ORDER = ("acoustic_cruise", "acoustic_high")


class ContactAnalyzer:
    """Bounded catalog browser with no game-state or observation dependency."""

    mode = "browser"

    def __init__(self, tr=widgets.IDENTITY_TR, *, projection=None,
                 packaged_assets: Mapping[str, tuple[str, bytes]] | None = None):
        self.tr = tr
        detached = project_contact_catalog() if projection is None else projection
        self.profiles = list(detached["profiles"])
        assets = load_contact_analysis_assets() if packaged_assets is None else packaged_assets
        self._asset_bytes = {
            route: payload for route, (mime, payload) in assets.items()
            if route.startswith(ASSET_ROUTE_PREFIX) and mime == "image/png"
        }
        self.surface_cache: OrderedDict[str, pygame.Surface] = OrderedDict()
        self.filter_text = ""
        self.filtered = list(range(len(self.profiles)))
        self.listbox = widgets.ListBox(self._list_labels())
        self.detail_scroll = 0
        self.focus = "list"
        self.asset_index = 0
        self._key_text = ""
        self._rects: dict[str, pygame.Rect] = {}
        self._detail_visible = 1
        self._prepare_selected_image()

    @property
    def selected_profile(self):
        if not self.filtered:
            return None
        return self.profiles[self.filtered[self.listbox.selected]]

    def _list_labels(self):
        return [f"{self.profiles[index]['name']} [{self.profiles[index]['key']}]"
                for index in self.filtered]

    def _set_filter(self, value: str) -> None:
        self.filter_text = value[:MAX_FILTER_CHARS]
        query = self.filter_text.casefold()
        self.filtered = [
            index for index, profile in enumerate(self.profiles)
            if not query or query in " ".join((profile["key"], profile["name"],
                                                profile["resource"])).casefold()
        ]
        self.listbox.selected = 0
        self.listbox.scroll = 0
        self.listbox.set_items(self._list_labels())
        self.detail_scroll = 0
        self.asset_index = 0
        self._prepare_selected_image()

    def _asset_kinds(self):
        profile = self.selected_profile
        if profile is None:
            return []
        return [kind for kind in _ASSET_ORDER if kind in profile["assets"]]

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
        profile = self.selected_profile
        self._decode_surface(profile["assets"][kinds[self.asset_index]])

    def _selection_changed(self) -> None:
        self.detail_scroll = 0
        self.asset_index = 0
        self._prepare_selected_image()

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
            ("analyzer.variant", reference["variant"]),
            ("analyzer.years", [reference["variant_year"], reference["refit_year"]]),
            ("analyzer.aliases", reference["aliases"]),
            ("analyzer.roles", reference["roles"]),
            ("analyzer.hull", reference["hull_type"]),
            ("analyzer.displacement", reference["displacement_tonnes"]),
            ("analyzer.length", reference["length_m"]),
            ("analyzer.beam", reference["beam_overall_m"] or reference["beam_waterline_m"]),
            ("analyzer.draft", reference["draft_m"]),
            ("analyzer.crew", reference["ship_crew"]),
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
            if event.key == pygame.K_TAB:
                self.focus = "detail" if self.focus == "list" else "list"
                return True
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                kinds = self._asset_kinds()
                if kinds:
                    self.asset_index = (self.asset_index + (-1 if event.key == pygame.K_LEFT else 1)) % len(kinds)
                    self._prepare_selected_image()
                return True
            if event.key == pygame.K_BACKSPACE:
                self._set_filter(self.filter_text[:-1])
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
            char = getattr(event, "unicode", "")
            if char and char.isprintable() and len(self.filter_text) < MAX_FILTER_CHARS:
                self._set_filter(self.filter_text + char)
                self._key_text = char
                return True
        if event.type == pygame.TEXTINPUT:
            text = "".join(char for char in getattr(event, "text", "") if char.isprintable())
            if text == self._key_text:
                self._key_text = ""
                return True
            self._key_text = ""
            if text:
                self._set_filter(self.filter_text + text)
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
            for index, tab in enumerate(self._rects.get("asset_tabs", ())):
                if tab.collidepoint(position):
                    self.asset_index = index
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
        widgets.draw_text(surface, self.tr("analyzer.read_only"),
                          (bounds.width - 430, 18, 410, 34), color=widgets.PALETTE.focus,
                          size=13, bold=True, align="right")
        footer = pygame.Rect(0, bounds.height - 42, bounds.width, 42)
        content = pygame.Rect(20, 66, bounds.width - 40, footer.y - 76)
        left = pygame.Rect(content.x, content.y, 390, content.height)
        left_inner = widgets.panel(surface, left, "analyzer.contacts", tr=self.tr)
        filter_rect = pygame.Rect(left_inner.x, left_inner.y, left_inner.width, 34)
        pygame.draw.rect(surface, widgets.PALETTE.background, filter_rect)
        pygame.draw.rect(surface, widgets.PALETTE.focus, filter_rect, 1)
        filter_value = self.filter_text or self.tr("analyzer.filter")
        widgets.draw_text(surface, raw_text(filter_value), filter_rect.inflate(-8, 0),
                          color=(widgets.PALETTE.text if self.filter_text else widgets.PALETTE.dim),
                          size=14)
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
            image_box = pygame.Rect(inner.x, inner.y + 38, 324, 300)
            pygame.draw.rect(surface, widgets.PALETTE.background, image_box)
            pygame.draw.rect(surface, widgets.PALETTE.border, image_box, 1)
            kinds = self._asset_kinds()
            if kinds:
                kind = kinds[self.asset_index]
                route = profile["assets"][kind]
                image = self.surface_cache.get(route)
                if image is not None:
                    image_rect = image.get_rect(midtop=(image_box.centerx,
                                                        image_box.y + 4))
                    surface.blit(image, image_rect)
                legend_y = image_box.y + 187
                legend_h = 34 if layout.text_scale() > 1.0 else 30
                spectrum_legend = pygame.Rect(image_box.x + 6, legend_y,
                                               image_box.width - 12, legend_h)
                hypothesis_legend = pygame.Rect(image_box.x + 6,
                                                 spectrum_legend.bottom,
                                                 image_box.width - 12,
                                                 image_box.bottom - 30 - spectrum_legend.bottom)
                self._rects["spectrum_legend"] = spectrum_legend
                self._rects["hypothesis_legend"] = hypothesis_legend
                layout.blit_block(surface, self.tr("analyzer.spectrum_legend"),
                                  *spectrum_legend, color=widgets.PALETTE.dim,
                                  size=11, min_size=9)
                layout.blit_block(surface, self.tr("analyzer.hypothesis_legend"),
                                  *hypothesis_legend, color=widgets.PALETTE.dim,
                                  size=11, min_size=9)
                tab_width = max(1, image_box.width // len(kinds))
                tabs = []
                for index, asset_kind in enumerate(kinds):
                    tab = pygame.Rect(image_box.x + index * tab_width, image_box.bottom - 30,
                                      tab_width, 30)
                    tabs.append(tab)
                    if index == self.asset_index:
                        pygame.draw.rect(surface, widgets.PALETTE.raised, tab)
                    widgets.draw_text(surface, self.tr("analyzer." + asset_kind), tab,
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
        widgets.draw_footer(surface, footer,
                            ("analyzer.filter_hint", "analyzer.select_hint",
                             "analyzer.image_hint", "analyzer.scroll_hint",
                             "analyzer.exit_hint"), tr=self.tr)

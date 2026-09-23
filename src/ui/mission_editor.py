"""Standalone mission browser/editor/controller with static map preview."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable, Mapping

import pygame

from src.core.i18n import raw_text, translation_scope
from src.core.mission_definition import (MISSION_FIELD_METADATA, MissionDefinition,
                                         default_mission)
from src.data.user_content import ContentRecord, UserContentStore
from src.data.validation import (ContentValidationError, localized_error,
                                 localized_issue)
from src.ui import editor_widgets as widgets


class MissionEditor:
    """Mission authoring UI independent of the running game.

    Structured mutation methods are intentionally available separately from
    pygame input so keyboard UI, tests, and a future menu integration use the
    same validation and persistence workflow.
    """

    tabs = ("overview", "world", "units", "objective", "events", "preview")

    def __init__(self, builtins: Mapping[str, Mapping[str, Any]] | None = None,
                 store: UserContentStore | None = None, tr=widgets.IDENTITY_TR,
                 profile_keys: Iterable[str] | None = None):
        self.tr = tr
        self.store = store or UserContentStore()
        self.builtins = {key: copy.deepcopy(dict(value))
                         for key, value in (builtins or {}).items()}
        self.profile_keys = set(profile_keys) if profile_keys is not None else None
        self.records: list[ContentRecord] = []
        self.listbox = widgets.ListBox()
        self.mode = "browser"
        self.tab_index = 0
        self.current: MissionDefinition | None = None
        self.status = ""
        self.fields = widgets.FieldList()
        self.exact_box = widgets.ListBox()
        self.group_box = widgets.ListBox()
        self.event_box = widgets.ListBox()
        self.unit_kind = "exact"
        self._rects: dict[str, pygame.Rect] = {}
        self._delete_pending: tuple[str, int] | None = None
        self.path_action: str | None = None
        self.path_input = widgets.TextField(maximum=1024)
        self.focus_area = "fields"
        self.refresh()

    def refresh(self) -> None:
        records = [ContentRecord(key, "mission", value, True)
                   for key, value in sorted(self.builtins.items())]
        records.extend(self.store.list("mission"))
        self.records = records
        self.listbox.set_items([f"{'[built-in]' if item.builtin else '[user]'} {item.key}"
                                for item in records])

    @property
    def selected(self) -> ContentRecord | None:
        return self.records[self.listbox.selected] if self.records else None

    @property
    def tab(self) -> str:
        return self.tabs[self.tab_index]

    @property
    def field_metadata(self):
        return MISSION_FIELD_METADATA

    def new(self, key: str = "user.new_mission") -> MissionDefinition:
        self.current = MissionDefinition(default_mission(key))
        self.mode = "editor"
        self._sync_fields()
        return self.current

    def open_selected(self) -> MissionDefinition | None:
        record = self.selected
        if record is None:
            return None
        self.current = MissionDefinition(record.data)
        if record.builtin:
            self.current = self.current.clone("user.clone")
            self.status = self.tr("editor.read_only_clone")
        self.mode = "editor"
        self._sync_fields()
        return self.current

    def clone_selected(self, key: str) -> MissionDefinition:
        record = self.selected
        if record is None:
            raise ValueError("no selected mission")
        self.current = MissionDefinition(record.data).clone(key)
        self.mode = "editor"
        self._sync_fields()
        return self.current

    def set_value(self, path: str, value: Any) -> None:
        """Set an existing dotted dictionary path (for form/widget adapters)."""
        if self.current is None:
            raise ValueError("no open mission")
        parts = path.split(".")
        target: Any = self.current.data
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                raise KeyError(path)
            target = target[part]
        if not isinstance(target, dict) or parts[-1] not in target:
            raise KeyError(path)
        target[parts[-1]] = value

    def add_sector(self, sector_id: str, x: float, y: float,
                   width: float, height: float) -> dict[str, Any]:
        sector = {"id": sector_id, "x": x, "y": y, "width": width, "height": height}
        self._data()["world"].setdefault("sectors", []).append(sector)
        return sector

    def add_exact_unit(self, unit_id: str, profile: str, side: str, *,
                       x: float | None = None, y: float | None = None,
                       sector: str | None = None, course_deg: float = 0,
                       speed_kn: float = 0, depth_m: float | None = None) -> dict[str, Any]:
        if sector is None:
            placement = {"kind": "fixed", "x": x, "y": y}
        else:
            placement = {"kind": "sector", "sector": sector}
        unit = {"id": unit_id, "profile": profile, "side": side,
                "placement": placement, "course_deg": course_deg, "speed_kn": speed_kn}
        if depth_m is not None:
            unit["depth_m"] = depth_m
        self._data()["units"]["exact"].append(unit)
        return unit

    def add_random_group(self, group_id: str, profiles: Iterable[str], side: str,
                         count: tuple[int, int] | list[int], *,
                         sector: str | None = None, x: float | None = None,
                         y: float | None = None) -> dict[str, Any]:
        placement = ({"kind": "sector", "sector": sector} if sector is not None
                     else {"kind": "fixed", "x": x, "y": y})
        group = {"id": group_id, "profiles": list(profiles), "side": side,
                 "count": list(count), "placement": placement}
        self._data()["units"]["random_groups"].append(group)
        return group

    def add_event(self, event_id: str, at_s: float, event_type: str, **values) -> dict[str, Any]:
        event = {"id": event_id, "at_s": at_s, "type": event_type, **values}
        self._data()["events"].append(event)
        return event

    def _data(self) -> dict[str, Any]:
        if self.current is None:
            raise ValueError("no open mission")
        return self.current.data

    def validate(self):
        if self.current is None:
            return []
        return self.current.validate(self.profile_keys)

    def preview(self, seed: int | None = None) -> dict[str, Any]:
        if self.current is None:
            raise ValueError("no open mission")
        return self.current.preview(seed)

    def save(self) -> Path:
        if self.current is None:
            raise ValueError("no open mission")
        problems = self.validate()
        if problems:
            raise ContentValidationError(problems)
        path = self.store.save("mission", self.current.data)
        self.status = self.tr("editor.saved")
        self.refresh()
        return path

    def export_bundle(self, path: str | Path, *, include_all: bool = False) -> Path:
        if include_all:
            missions = [record.data for record in self.store.list("mission")]
        elif self.current is not None:
            missions = [self.current.to_dict()]
        else:
            missions = []
        return self.store.export_bundle(path, missions=missions)

    def import_bundle(self, path: str | Path, *, overwrite: bool = False) -> list[ContentRecord]:
        records = self.store.import_bundle(path, overwrite=overwrite)
        self.refresh()
        return records

    @staticmethod
    def _next_id(values: Iterable[Mapping[str, Any]], prefix: str) -> str:
        used = {str(value.get("id", "")) for value in values}
        number = 1
        while f"{prefix}{number}" in used:
            number += 1
        return f"{prefix}{number}"

    def _sync_fields(self) -> None:
        if self.current is None:
            self.fields.set_rows(())
            return
        data = self.current.data
        if self.tab == "overview":
            subset = {key: data[key] for key in ("key", "name", "description", "seed")}
            rows = widgets.mapping_rows(subset)
            # The temporary dictionary needs setters aimed at the actual model.
            for row in rows:
                key = row.path
                row.setter = lambda value, field=key: data.__setitem__(field, value)
        elif self.tab == "world":
            rows = (widgets.mapping_rows(data["world"], "world")
                    + widgets.mapping_rows(data["player"], "player")
                    + widgets.mapping_rows(data["environment"], "environment"))
            if "reference" not in data["world"]:
                rows.append(widgets.FieldRow("world.reference", "field.reference", "",
                                             lambda value: data["world"].__setitem__("reference", value)))
        elif self.tab == "objective":
            rows = widgets.mapping_rows(data["objective"], "objective")
        elif self.tab == "units":
            exact = data["units"]["exact"]
            groups = data["units"]["random_groups"]
            self.exact_box.set_items([str(item.get("id", "?")) for item in exact])
            self.group_box.set_items([str(item.get("id", "?")) for item in groups])
            if self.unit_kind == "random_groups" and groups:
                rows = widgets.mapping_rows(groups[self.group_box.selected],
                                             f"units.random_groups[{self.group_box.selected}]")
            elif exact:
                self.unit_kind = "exact"
                rows = widgets.mapping_rows(exact[self.exact_box.selected],
                                             f"units.exact[{self.exact_box.selected}]")
            elif groups:
                self.unit_kind = "random_groups"
                rows = widgets.mapping_rows(groups[self.group_box.selected],
                                             f"units.random_groups[{self.group_box.selected}]")
            else:
                rows = []
            selected_values = exact if self.unit_kind == "exact" else groups
            selected_index = self.exact_box.selected if self.unit_kind == "exact" else self.group_box.selected
            if selected_values:
                selected_path = (f"units.exact[{selected_index}]" if self.unit_kind == "exact"
                                 else f"units.random_groups[{selected_index}]")
                selected_item = selected_values[selected_index]
                placement = selected_item.get("placement", {})
                if isinstance(placement, dict):
                    optional = (("sector", ""), ("x", 0.0), ("y", 0.0))
                    for key, initial in optional:
                        if key not in placement:
                            rows.append(widgets.FieldRow(
                                f"{selected_path}.placement.{key}", "field." + key, initial,
                                lambda value, target=placement, field=key: target.__setitem__(field, value)))
                if self.unit_kind == "exact" and "depth_m" not in selected_item:
                    rows.append(widgets.FieldRow(
                        f"{selected_path}.depth_m", "field.depth_m", 0.0,
                        lambda value, target=selected_item: target.__setitem__("depth_m", value)))
                rows.append(widgets.FieldRow(
                    selected_path, "field.json", selected_item,
                    lambda value, values=selected_values, index=selected_index: values.__setitem__(index, value)))
        elif self.tab == "events":
            events = data["events"]
            self.event_box.set_items([str(item.get("id", "?")) for item in events])
            rows = (widgets.mapping_rows(events[self.event_box.selected],
                                         f"events[{self.event_box.selected}]") if events else [])
            if events:
                index = self.event_box.selected
                selected_event = events[index]
                for key, initial in (("message", ""), ("target_id", ""),
                                     ("weather", "clear"), ("action", "complete")):
                    if key not in selected_event:
                        rows.append(widgets.FieldRow(
                            f"events[{index}].{key}", "field." + key, initial,
                            lambda value, target=selected_event, field=key: target.__setitem__(field, value)))
                rows.append(widgets.FieldRow(
                    f"events[{index}]", "field.json", selected_event,
                    lambda value, values=events, selected=index: values.__setitem__(selected, value)))
        else:
            rows = []
        self.fields.set_rows(rows)

    def _add_exact(self) -> None:
        values = self._data()["units"]["exact"]
        profile = sorted(self.profile_keys)[0] if self.profile_keys else "sub"
        unit_id = self._next_id(values + self._data()["units"]["random_groups"], "unit")
        self.add_exact_unit(unit_id, profile, "hostile", x=100.0, y=100.0,
                            course_deg=0.0, speed_kn=5.0, depth_m=50.0)
        self.exact_box.selected = len(values) - 1
        self.unit_kind = "exact"
        self.focus_area = "fields"

    def _add_group(self) -> None:
        values = self._data()["units"]["random_groups"]
        profile = sorted(self.profile_keys)[0] if self.profile_keys else "sub"
        group_id = self._next_id(self._data()["units"]["exact"] + values, "group")
        self.add_random_group(group_id, [profile], "hostile", [1, 1], x=100.0, y=100.0)
        self.group_box.selected = len(values) - 1
        self.unit_kind = "random_groups"
        self.focus_area = "fields"

    def _add_event_ui(self) -> None:
        events = self._data()["events"]
        self.add_event(self._next_id(events, "event"), 0.0, "message", message="New event",
                       target_id="", weather="clear", action="complete")
        self.event_box.selected = len(events) - 1
        self.focus_area = "fields"

    def _delete_target(self) -> tuple[str, int] | None:
        if self.tab == "events" and self._data()["events"]:
            return "events", self.event_box.selected
        if self.tab == "units":
            if self.unit_kind == "exact" and self.exact_box.items:
                return "exact", self.exact_box.selected
            if self.group_box.items:
                return "random_groups", self.group_box.selected
        return None

    def _delete(self, target: tuple[str, int]) -> None:
        kind, index = target
        values = self._data()["events"] if kind == "events" else self._data()["units"][kind]
        if 0 <= index < len(values):
            del values[index]
        self._delete_pending = None
        self.status = self.tr("editor.deleted")
        self._sync_fields()

    def _begin_path(self, action: str) -> None:
        self.path_action = action
        self.path_input.value = str(self.store.root / "editor-bundle.json")
        self.path_input.selected_all = True
        self.status = self.tr("editor.enter_bundle_path")

    def _handle_path(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN and event.type != pygame.TEXTINPUT:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.path_action = None
            return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            try:
                if self.path_action == "export":
                    self.export_bundle(self.path_input.value)
                    self.status = self.tr("editor.path_result",
                                          action=self.tr("editor.exported"),
                                          path=self.path_input.value)
                else:
                    self.import_bundle(self.path_input.value)
                    self.status = self.tr("editor.path_result",
                                          action=self.tr("editor.imported"),
                                          path=self.path_input.value)
            except (ContentValidationError, OSError, ValueError) as exc:
                self.status = localized_error(exc, self.tr)
            self.path_action = None
            return True
        if event.type == pygame.TEXTINPUT:
            return self.path_input.handle_text(getattr(event, "text", ""))
        return self.path_input.handle_event(event)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if not x and not y:
                return False
            key = pygame.K_UP if y > 0 else pygame.K_DOWN if y < 0 else pygame.K_LEFT if x < 0 else pygame.K_RIGHT
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="")
        if self.path_action:
            return self._handle_path(event)
        if self.mode == "browser":
            changed = self.listbox.handle_event(event, self._rects.get("browser", pygame.Rect(28, 104, 424, 532)))
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.open_selected(); return True
                if event.key == pygame.K_n:
                    self.new(); return True
                if event.key == pygame.K_i and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                    self._begin_path("import"); return True
            return changed
        if self.fields.editing:
            if (event.type == pygame.KEYDOWN and event.key == pygame.K_s
                    and getattr(event, "mod", 0) & pygame.KMOD_CTRL):
                self.fields.apply_edit()
                if self.fields.editing:
                    self.status = self.fields.error
                else:
                    self._sync_fields()
                    try:
                        self.save()
                    except (ContentValidationError, OSError) as exc:
                        self.status = localized_error(exc, self.tr)
                return True
            handled = self.fields.handle_event(event, self._rects.get("fields", pygame.Rect(40, 150, 900, 450)))
            if self.fields.error:
                self.status = self.fields.error
            elif handled:
                self._sync_fields()
            return handled
        if self._delete_pending is not None:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_DELETE):
                self._delete(self._delete_pending); return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._delete_pending = None; self.status = ""; return True
            return True
        position = widgets.event_position(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and position:
            for index, rect in enumerate(self._rects.get("tabs", ())):
                if rect.collidepoint(position):
                    self.tab_index = index; self._sync_fields(); return True
            for name, box in (("exact", self.exact_box), ("groups", self.group_box), ("events", self.event_box)):
                rect = self._rects.get(name)
                if rect and rect.collidepoint(position):
                    box.handle_event(event, rect)
                    if name == "exact": self.unit_kind = "exact"
                    if name == "groups": self.unit_kind = "random_groups"
                    self.focus_area = name
                    self._sync_fields(); return True
            if self._rects.get("fields", pygame.Rect(0, 0, 0, 0)).collidepoint(position):
                self.focus_area = "fields"
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_TAB
                and self.tab in ("units", "events")):
            areas = ("events", "fields") if self.tab == "events" else ("exact", "groups", "fields")
            direction = -1 if getattr(event, "mod", 0) & pygame.KMOD_SHIFT else 1
            current = areas.index(self.focus_area) if self.focus_area in areas else len(areas) - 1
            self.focus_area = areas[(current + direction) % len(areas)]
            if self.focus_area == "exact": self.unit_kind = "exact"
            if self.focus_area == "groups": self.unit_kind = "random_groups"
            self._sync_fields()
            return True
        if self.focus_area != "fields" and event.type in (pygame.KEYDOWN, pygame.MOUSEWHEEL):
            box = {"exact": self.exact_box, "groups": self.group_box,
                   "events": self.event_box}.get(self.focus_area)
            rect = self._rects.get(self.focus_area)
            if box is not None and rect is not None:
                changed = box.handle_event(event, rect)
                if changed:
                    self._sync_fields()
                if event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_UP, pygame.K_DOWN, pygame.K_j, pygame.K_k,
                        pygame.K_HOME, pygame.K_END, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                    return True
        if self.fields.handle_event(event, self._rects.get("fields", pygame.Rect(40, 150, 900, 450))):
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.mode = "browser"; return True
            if event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                self.tab_index = (self.tab_index - 1) % len(self.tabs); self._sync_fields(); return True
            if event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN, pygame.K_TAB):
                direction = -1 if event.key == pygame.K_TAB and getattr(event, "mod", 0) & pygame.KMOD_SHIFT else 1
                self.tab_index = (self.tab_index + direction) % len(self.tabs); self._sync_fields(); return True
            if event.key == pygame.K_e and not getattr(event, "mod", 0) & pygame.KMOD_CTRL and self.tab == "units":
                self._add_exact(); self._sync_fields(); return True
            if event.key == pygame.K_g and self.tab == "units":
                self._add_group(); self._sync_fields(); return True
            if event.key == pygame.K_a and self.tab == "events":
                self._add_event_ui(); self._sync_fields(); return True
            if event.key == pygame.K_DELETE and self._delete_target() is not None:
                target = self._delete_target()
                if getattr(event, "mod", 0) & pygame.KMOD_SHIFT:
                    self._delete(target)
                else:
                    self._delete_pending = target
                    self.status = self.tr("editor.delete_confirm")
                return True
            if event.key == pygame.K_s and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                try:
                    self.save()
                except (ContentValidationError, OSError) as exc:
                    self.status = localized_error(exc, self.tr)
                return True
            if event.key == pygame.K_e and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                self._begin_path("export"); return True
            if event.key == pygame.K_i and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                self._begin_path("import"); return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        # Author-authored text must never enter translation/template parsing,
        # including when this editor is drawn inside Game's translation scope.
        with translation_scope(None):
            self._draw(surface)

    def _draw(self, surface: pygame.Surface) -> None:
        bounds = surface.get_rect()
        surface.fill(widgets.PALETTE.background)
        widgets.draw_text(surface, self.tr("editor.mission_title"),
                          (20, 15, bounds.width - 40, 40), size=24, bold=True)
        footer = pygame.Rect(0, max(0, bounds.height - 42), bounds.width, min(42, bounds.height))
        content = pygame.Rect(20, 66, max(1, bounds.width - 40), max(1, footer.y - 76))
        with widgets.clipped(surface, content):
            if self.mode == "browser":
                self._draw_browser(surface, content)
            elif self.current:
                self._draw_editor(surface, content)
        hints = (("editor.select_hint", "editor.open_hint", "editor.new_hint")
                  if self.mode == "browser" else
                  ("editor.arrow_hint", "editor.edit_hint", "editor.add_hint", "editor.remove_hint",
                   "editor.save_hint", "editor.bundle_hint", "editor.cancel_hint"))
        widgets.draw_footer(surface, footer, hints, tr=self.tr)
        if self.path_action:
            box = pygame.Rect(max(20, bounds.width // 6), bounds.height // 2 - 55,
                              max(1, bounds.width * 2 // 3), 110)
            inner = widgets.panel(surface, box, "editor.bundle_path", tr=self.tr)
            self.path_input.draw(surface, pygame.Rect(inner.x, inner.y + 5, inner.width, 34), focused=True)
        if self.status:
            widgets.draw_text(surface, raw_text(self.status), (bounds.width // 2, 18, bounds.width // 2 - 20, 28),
                              color=widgets.PALETTE.focus, align="right", size=13)

    def _draw_browser(self, surface: pygame.Surface, content: pygame.Rect) -> None:
        left = pygame.Rect(content.x, content.y, min(440, content.width), content.height)
        self._rects["browser"] = widgets.panel(surface, left, "editor.mission_library", tr=self.tr)
        self.listbox.draw(surface, self._rects["browser"])
        right = pygame.Rect(left.right + 12, content.y, max(1, content.right - left.right - 12), content.height)
        inner = widgets.panel(surface, right, "editor.brief", tr=self.tr)
        record = self.selected
        if not record:
            widgets.draw_text(surface, self.tr("editor.no_missions"), inner,
                              color=widgets.PALETTE.dim)
            return
        values = (record.key, record.data.get("name", ""), record.data.get("description", ""),
                  self.tr("editor.read_only" if record.builtin else "editor.user_mission"),
                  self.tr("editor.runtime_no"))
        for row, value in enumerate(values):
            widgets.draw_text(surface, raw_text(value),
                              (inner.x, inner.y + row * 32, inner.width, 28),
                              color=widgets.PALETTE.focus if row == 4 else widgets.PALETTE.text)

    def _draw_editor(self, surface: pygame.Surface, content: pygame.Rect) -> None:
        self._sync_fields()
        tab_h = 34
        tab_w = max(80, content.width // len(self.tabs))
        tab_rects = []
        for index, name in enumerate(self.tabs):
            rect = pygame.Rect(content.x + index * tab_w, content.y,
                               min(tab_w, content.right - (content.x + index * tab_w)), tab_h)
            pygame.draw.rect(surface, widgets.PALETTE.raised if index == self.tab_index else widgets.PALETTE.panel, rect)
            pygame.draw.rect(surface, widgets.PALETTE.focus if index == self.tab_index else widgets.PALETTE.border, rect, 1)
            widgets.draw_text(surface, self.tr("editor." + name), rect, align="center", size=13)
            tab_rects.append(rect)
        self._rects["tabs"] = tab_rects
        body = pygame.Rect(content.x, content.y + tab_h + 8, content.width, content.height - tab_h - 8)
        if self.tab == "preview":
            self._draw_preview(surface, body)
            return
        inner = widgets.panel(surface, body, "editor." + self.tab, tr=self.tr)
        field_area = pygame.Rect(inner.x, inner.y, inner.width, max(1, inner.height - 32))
        if self.tab == "units":
            list_width = min(285, max(180, inner.width // 4))
            half = max(50, (field_area.height - 34) // 2)
            widgets.draw_text(surface, self.tr("editor.exact_units"), (inner.x, inner.y, list_width, 24), size=13)
            exact_rect = pygame.Rect(inner.x, inner.y + 25, list_width, half - 25)
            widgets.draw_text(surface, self.tr("editor.seeded_groups"), (inner.x, exact_rect.bottom + 4, list_width, 24), size=13)
            group_rect = pygame.Rect(inner.x, exact_rect.bottom + 29, list_width,
                                     max(1, field_area.bottom - exact_rect.bottom - 29))
            self._rects.update(exact=exact_rect, groups=group_rect)
            self.exact_box.draw(surface, exact_rect)
            self.group_box.draw(surface, group_rect)
            field_area = pygame.Rect(inner.x + list_width + 12, inner.y,
                                     max(1, inner.width - list_width - 12), field_area.height)
        elif self.tab == "events":
            list_width = min(285, max(180, inner.width // 4))
            event_rect = pygame.Rect(inner.x, inner.y, list_width, field_area.height)
            self._rects["events"] = event_rect
            self.event_box.draw(surface, event_rect)
            field_area = pygame.Rect(event_rect.right + 12, inner.y,
                                     max(1, inner.right - event_rect.right - 12), field_area.height)
        self._rects["fields"] = field_area
        self.fields.draw(surface, field_area, tr=self.tr)
        problems = self.validate()
        message = (localized_issue(problems[0], self.tr) if problems else
                   self.tr("editor.valid_data"))
        widgets.draw_text(surface, message,
                           (inner.x, inner.bottom - 30, inner.width, 26),
                          color=widgets.PALETTE.danger if problems else widgets.PALETTE.focus)

    def _draw_preview(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        inner = widgets.panel(surface, rect, "editor.preview", tr=self.tr)
        try:
            preview = self.preview()
        except ContentValidationError as exc:
            widgets.draw_text(surface, localized_error(exc, self.tr), inner,
                              color=widgets.PALETTE.danger)
            return
        map_size = min(inner.height, inner.width - 260)
        map_rect = pygame.Rect(inner.x, inner.y, max(1, map_size), max(1, map_size))
        pygame.draw.rect(surface, (9, 28, 35), map_rect)
        pygame.draw.rect(surface, widgets.PALETTE.border, map_rect, 1)
        world_size = preview["world_size_nm"]
        with widgets.clipped(surface, map_rect):
            for sector in preview["sectors"]:
                box = pygame.Rect(map_rect.x + sector["x"] / world_size * map_rect.width,
                                  map_rect.y + sector["y"] / world_size * map_rect.height,
                                  sector["width"] / world_size * map_rect.width,
                                  sector["height"] / world_size * map_rect.height)
                pygame.draw.rect(surface, widgets.PALETTE.border, box, 1)
            colors = {"friendly": widgets.PALETTE.friendly, "neutral": widgets.PALETTE.neutral,
                      "hostile": widgets.PALETTE.hostile}
            for marker in preview["markers"]:
                point = (round(map_rect.x + marker["x"] / world_size * map_rect.width),
                         round(map_rect.y + marker["y"] / world_size * map_rect.height))
                pygame.draw.circle(surface, colors.get(marker["side"], widgets.PALETTE.text), point, 5, 1)
        details = pygame.Rect(map_rect.right + 14, inner.y, max(1, inner.right - map_rect.right - 14), inner.height)
        lines = (self.tr("editor.preview_seed", seed=preview["seed"]),
                 self.tr("editor.preview_markers", count=len(preview["markers"])),
                 self.tr("editor.preview_events", count=len(preview["events"])),
                 self.tr("editor.static_only"), self.tr("editor.runtime_no"))
        for row, line in enumerate(lines):
            widgets.draw_text(surface, line,
                              (details.x, details.y + row * 30, details.width, 26),
                              color=widgets.PALETTE.focus if row >= 3 else widgets.PALETTE.text)

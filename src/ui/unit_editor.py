"""Standalone unit-profile model and pygame browser/editor controller."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pygame

from src.core.i18n import display_value, raw_text, translation_scope
from src.data.catalog import ACOUSTIC_FIELDS
from src.data.user_content import ContentRecord, UserContentStore
from src.data.validation import (ContentValidationError, ValidationIssue, enum,
                                 finite_number, integer, issue, pair, text,
                                 unique, validate_user_key, localized_error,
                                 localized_issue)
from src.ui import editor_widgets as widgets


UNIT_VERSION = 1
PROFILE_KINDS = ("sub", "surface", "aircraft", "animal", "torpedo", "decoy")


@dataclass(frozen=True)
class UnitFieldMetadata:
    supported: bool
    effective: bool
    note: str = ""


UNIT_FIELD_METADATA = {
    "identity": UnitFieldMetadata(True, False, "User profile loading is not integrated yet."),
    "movement": UnitFieldMetadata(True, False),
    "behavior": UnitFieldMetadata(True, False),
    "weapons": UnitFieldMetadata(True, False),
    "acoustic": UnitFieldMetadata(True, False),
    "spawn_weight": UnitFieldMetadata(True, False),
}

_UNIT_KIND_FIELDS = {
    "sub": ("speed_kn", "max_depth_m", "torpedoes", "quiet", "aggression", "spawn_weight", "acoustic"),
    "surface": ("category", "hostile", "speed_kn", "callsigns", "esm_prob", "asm_salvo",
                "asm_cooldown_s", "loiter_nm", "spawn_weight", "acoustic"),
    "aircraft": ("nation", "aircraft_kind", "speed_kn", "esm", "esm_range_nm", "loiter_nm",
                 "spawn_weight", "signature_text"),
    "animal": ("depth_min", "depth_max", "speed_kn", "quiet", "size_nm", "spawn_weight",
               "lines", "signature_text"),
    "torpedo": ("used_by", "speed_kn", "range_nm", "hit_dist_nm", "acoustic"),
    "decoy": ("life_s", "speed_kn", "cooldown_s", "chance", "lines", "signature_text"),
}


def unit_field_metadata(kind: str) -> dict[str, UnitFieldMetadata]:
    """Return support/effectiveness metadata for every top-level profile field."""
    if kind not in PROFILE_KINDS:
        raise ValueError(f"unknown profile kind: {kind}")
    fields = ("version", "key", "profile_kind", "name") + _UNIT_KIND_FIELDS[kind]
    return {field: UnitFieldMetadata(True, False,
                                     "Editor-supported; runtime integration pending.")
            for field in fields}


def _acoustic_default(category: str) -> dict[str, Any]:
    return {"label": "New signature", "propulsion": "unknown", "blades": [5],
            "rpm_range": [80.0, 200.0], "tonal_band_hz": [10.0, 80.0],
            "cavitation_tendency": 0.5, "category": category,
            "secondary_tonals": [], "broadband": [0.3, 30.0, 250.0],
            "signature_text": ""}


def default_unit(kind: str = "sub", key: str = "user.new_unit") -> dict[str, Any]:
    if kind not in PROFILE_KINDS:
        raise ValueError(f"unknown profile kind: {kind}")
    common = {"version": UNIT_VERSION, "key": key, "profile_kind": kind,
              "name": "New unit"}
    details = {
        "sub": {"speed_kn": [6.0, 12.0], "max_depth_m": 250.0,
                "torpedoes": 4, "quiet": 0.8, "aggression": 0.5,
                "spawn_weight": 1.0, "acoustic": _acoustic_default("U_BOOT")},
        "surface": {"category": "KAMPFSCHIFF", "hostile": True,
                    "speed_kn": [10.0, 25.0], "callsigns": [], "esm_prob": 1.0,
                    "asm_salvo": [0, 0], "asm_cooldown_s": 900.0,
                    "loiter_nm": 20.0, "spawn_weight": 1.0,
                    "acoustic": _acoustic_default("KAMPFSCHIFF")},
        "aircraft": {"nation": "ZIVIL", "aircraft_kind": "civil",
                     "speed_kn": 300.0, "esm": False, "esm_range_nm": 0.0,
                     "loiter_nm": [0.0, 0.0], "spawn_weight": 1.0,
                     "signature_text": ""},
        "animal": {"depth_min": 10.0, "depth_max": 50.0, "speed_kn": 2.0,
                   "quiet": 0.5, "size_nm": 0.3, "spawn_weight": 1.0,
                   "lines": [], "signature_text": ""},
        "torpedo": {"used_by": "enemy", "speed_kn": 28.0, "range_nm": 30.0,
                    "hit_dist_nm": 0.25, "acoustic": None},
        "decoy": {"life_s": 45.0, "speed_kn": 8.0, "cooldown_s": 60.0,
                  "chance": 0.5, "lines": [], "signature_text": ""},
    }
    return common | details[kind]


def _tonals(value: Any, path: str) -> list[ValidationIssue]:
    if not isinstance(value, list):
        return [issue(path, "array", "must be an array")]
    problems = []
    for index, tonal in enumerate(value):
        base = f"{path}[{index}]"
        if not isinstance(tonal, (list, tuple)) or len(tonal) != 3:
            problems.append(issue(base, "triple", "must be [frequency, amplitude, width]"))
            continue
        problems += finite_number(tonal[0], f"{base}[0]", minimum=0.01, maximum=100000)
        problems += finite_number(tonal[1], f"{base}[1]", minimum=0, maximum=1)
        problems += finite_number(tonal[2], f"{base}[2]", minimum=0.01, maximum=10000)
    return problems


def _validate_acoustic(value: Any, path: str = "acoustic") -> list[ValidationIssue]:
    if not isinstance(value, Mapping):
        return [issue(path, "object", "must be an acoustic object")]
    problems = []
    # Shipped dataclass clones retain the source signature key as descriptive data.
    fields = tuple(sorted(ACOUSTIC_FIELDS | {"key"}))
    for field in value:
        if field not in fields:
            problems += enum(field, f"{path}.{field}", fields)
    if "key" in value:
        problems += text(value["key"], f"{path}.key", maximum=80)
    problems += text(value.get("label"), f"{path}.label", maximum=80)
    problems += text(value.get("propulsion"), f"{path}.propulsion", maximum=100)
    blades = value.get("blades")
    if not isinstance(blades, list):
        problems.append(issue(f"{path}.blades", "array", "must be an array"))
    else:
        problems += unique(blades, f"{path}.blades")
        for index, blade in enumerate(blades):
            problems += integer(blade, f"{path}.blades[{index}]", minimum=1, maximum=20)
    problems += pair(value.get("rpm_range"), f"{path}.rpm_range", minimum=0, maximum=100000)
    problems += pair(value.get("tonal_band_hz"), f"{path}.tonal_band_hz", minimum=0, maximum=100000)
    problems += finite_number(value.get("cavitation_tendency"),
                              f"{path}.cavitation_tendency", minimum=0, maximum=1)
    problems += enum(value.get("category"), f"{path}.category",
                     ("U_BOOT", "KAMPFSCHIFF", "TANKER", "PASSAGIER", "FRACHT",
                      "SONSTIGES", "FAHRZEUG", "BIOLOGISCH"))
    problems += _tonals(value.get("secondary_tonals"), f"{path}.secondary_tonals")
    broadband = value.get("broadband")
    if broadband is not None:
        if not isinstance(broadband, (list, tuple)) or len(broadband) != 3:
            problems.append(issue(f"{path}.broadband", "triple", "must be [level, low, high] or null"))
        else:
            problems += finite_number(broadband[0], f"{path}.broadband[0]", minimum=0, maximum=1)
            problems += finite_number(broadband[1], f"{path}.broadband[1]", minimum=0, maximum=100000)
            problems += finite_number(broadband[2], f"{path}.broadband[2]", minimum=0, maximum=100000)
            if not problems and broadband[1] >= broadband[2]:
                problems.append(issue(f"{path}.broadband", "order", "low frequency must be below high frequency"))
            elif all(isinstance(v, (int, float)) for v in broadband[1:]) and broadband[1] >= broadband[2]:
                problems.append(issue(f"{path}.broadband", "order", "low frequency must be below high frequency"))
    problems += text(value.get("signature_text", ""), f"{path}.signature_text",
                     required=False, maximum=500)
    return problems


def validate_unit(data: Mapping[str, Any]) -> list[ValidationIssue]:
    if not isinstance(data, Mapping):
        return [issue("", "object", "unit profile must be an object")]
    problems = []
    problems += integer(data.get("version"), "version", minimum=UNIT_VERSION, maximum=UNIT_VERSION)
    problems += validate_user_key(data.get("key"))
    problems += enum(data.get("profile_kind"), "profile_kind", PROFILE_KINDS)
    problems += text(data.get("name"), "name", maximum=80)
    kind = data.get("profile_kind")
    fields = ("version", "key", "profile_kind", "name")
    if isinstance(kind, str) and kind in _UNIT_KIND_FIELDS:
        fields += _UNIT_KIND_FIELDS[kind]
    for field in data:
        if field not in fields:
            problems += enum(field, str(field), fields)
    if kind == "sub":
        problems += pair(data.get("speed_kn"), "speed_kn", minimum=0, maximum=1000)
        problems += finite_number(data.get("max_depth_m"), "max_depth_m", minimum=0, maximum=2000)
        problems += integer(data.get("torpedoes"), "torpedoes", minimum=0, maximum=100)
        problems += finite_number(data.get("quiet"), "quiet", minimum=0, maximum=1)
        problems += finite_number(data.get("aggression"), "aggression", minimum=0, maximum=1)
        problems += finite_number(data.get("spawn_weight"), "spawn_weight", minimum=0, maximum=100000)
        problems += _validate_acoustic(data.get("acoustic"))
    elif kind == "surface":
        problems += enum(data.get("category"), "category",
                         ("TANKER", "PASSAGIER", "FRACHT", "SONSTIGES", "KAMPFSCHIFF"))
        if not isinstance(data.get("hostile"), bool):
            problems.append(issue("hostile", "boolean", "must be true or false"))
        problems += pair(data.get("speed_kn"), "speed_kn", minimum=0, maximum=1000)
        callsigns = data.get("callsigns")
        if not isinstance(callsigns, list):
            problems.append(issue("callsigns", "array", "must be an array"))
        else:
            problems += unique(callsigns, "callsigns")
            for index, callsign in enumerate(callsigns):
                problems += text(callsign, f"callsigns[{index}]", maximum=32)
        problems += finite_number(data.get("esm_prob"), "esm_prob", minimum=0, maximum=1)
        problems += pair(data.get("asm_salvo"), "asm_salvo", minimum=0, maximum=100,
                         integer_values=True)
        problems += finite_number(data.get("asm_cooldown_s"), "asm_cooldown_s", minimum=0,
                                  maximum=7 * 24 * 3600)
        problems += finite_number(data.get("loiter_nm"), "loiter_nm", minimum=0, maximum=5000)
        problems += finite_number(data.get("spawn_weight"), "spawn_weight", minimum=0, maximum=100000)
        problems += _validate_acoustic(data.get("acoustic"))
    elif kind == "aircraft":
        problems += text(data.get("nation"), "nation", maximum=32)
        problems += enum(data.get("aircraft_kind"), "aircraft_kind", ("civil", "military"))
        problems += finite_number(data.get("speed_kn"), "speed_kn", minimum=0.01, maximum=5000)
        if not isinstance(data.get("esm"), bool):
            problems.append(issue("esm", "boolean", "must be true or false"))
        problems += finite_number(data.get("esm_range_nm"), "esm_range_nm", minimum=0, maximum=5000)
        problems += pair(data.get("loiter_nm"), "loiter_nm", minimum=0, maximum=5000)
        problems += finite_number(data.get("spawn_weight"), "spawn_weight", minimum=0, maximum=100000)
        problems += text(data.get("signature_text", ""), "signature_text", required=False, maximum=500)
    elif kind == "animal":
        problems += finite_number(data.get("depth_min"), "depth_min", minimum=0, maximum=2000)
        problems += finite_number(data.get("depth_max"), "depth_max", minimum=0, maximum=2000)
        if isinstance(data.get("depth_min"), (int, float)) and isinstance(data.get("depth_max"), (int, float)) \
                and data["depth_min"] > data["depth_max"]:
            problems.append(issue("depth", "order", "minimum depth must not exceed maximum depth"))
        problems += finite_number(data.get("speed_kn"), "speed_kn", minimum=0, maximum=1000)
        problems += finite_number(data.get("quiet"), "quiet", minimum=0, maximum=1)
        problems += finite_number(data.get("size_nm"), "size_nm", minimum=0.001, maximum=100)
        problems += finite_number(data.get("spawn_weight"), "spawn_weight", minimum=0, maximum=100000)
        problems += _tonals(data.get("lines"), "lines")
        problems += text(data.get("signature_text", ""), "signature_text", required=False, maximum=500)
    elif kind == "torpedo":
        problems += enum(data.get("used_by"), "used_by", ("frigate", "helo", "enemy"))
        problems += finite_number(data.get("speed_kn"), "speed_kn", minimum=0.01, maximum=1000)
        problems += finite_number(data.get("range_nm"), "range_nm", minimum=0.001, maximum=5000)
        problems += finite_number(data.get("hit_dist_nm"), "hit_dist_nm", minimum=0.001, maximum=100)
        if data.get("acoustic") is not None:
            problems += _validate_acoustic(data.get("acoustic"))
    elif kind == "decoy":
        problems += finite_number(data.get("life_s"), "life_s", minimum=0.01, maximum=7 * 24 * 3600)
        problems += finite_number(data.get("speed_kn"), "speed_kn", minimum=0, maximum=1000)
        problems += finite_number(data.get("cooldown_s"), "cooldown_s", minimum=0, maximum=7 * 24 * 3600)
        problems += finite_number(data.get("chance"), "chance", minimum=0, maximum=1)
        problems += _tonals(data.get("lines"), "lines")
        problems += text(data.get("signature_text", ""), "signature_text", required=False, maximum=500)
    return problems


def _plain_builtin(profile: Any, kind: str) -> dict[str, Any]:
    source = asdict(profile) if is_dataclass(profile) else copy.deepcopy(dict(profile))
    source.pop("key", None)
    if kind == "surface" and "hostile" not in source:
        # Unit-editor v1 persists this legacy authoring field. Runtime side is
        # mission-owned and does not come from the platform profile.
        source["hostile"] = source.get("category") == "KAMPFSCHIFF"
    if kind == "aircraft" and "kind" in source:
        source["aircraft_kind"] = source.pop("kind")
    if "acoustic" in source and source["acoustic"] is not None:
        acoustic = source["acoustic"]
        if is_dataclass(acoustic):
            acoustic = asdict(acoustic)
        acoustic = dict(acoustic)
        if "blade_counts" in acoustic:
            acoustic["blades"] = acoustic.pop("blade_counts")
        source["acoustic"] = acoustic
    # JSON profiles use lists; dataclass profiles use tuples.
    def lists(value):
        if isinstance(value, tuple):
            return [lists(item) for item in value]
        if isinstance(value, dict):
            return {key: lists(item) for key, item in value.items()}
        return value
    return lists(source)


def catalog_builtins(catalog: Any) -> dict[str, tuple[str, Any]]:
    """Adapt a ContactCatalog-like object to the editor's read-only library."""
    result = {}
    for attribute, kind in (("subs", "sub"), ("surfaces", "surface"),
                            ("aircraft", "aircraft"), ("animals", "animal"),
                            ("torpedoes", "torpedo"), ("decoys", "decoy")):
        result.update({key: (kind, profile)
                       for key, profile in getattr(catalog, attribute, {}).items()})
    return result


class UnitDefinition:
    def __init__(self, data: Mapping[str, Any] | None = None):
        self.data = copy.deepcopy(dict(data)) if data is not None else default_unit()

    @property
    def field_metadata(self):
        kind = self.data.get("profile_kind")
        return unit_field_metadata(kind) if kind in PROFILE_KINDS else UNIT_FIELD_METADATA

    def validate(self) -> list[ValidationIssue]:
        return validate_unit(self.data)

    def clone(self, key: str) -> "UnitDefinition":
        value = copy.deepcopy(self.data); value["key"] = key
        return UnitDefinition(value)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)

    def set_value(self, path: str, value: Any) -> None:
        parts = path.split(".")
        target: Any = self.data
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                raise KeyError(path)
            target = target[part]
        if not isinstance(target, dict) or parts[-1] not in target:
            raise KeyError(path)
        target[parts[-1]] = value

    @classmethod
    def clone_builtin(cls, profile: Any, kind: str, key: str) -> "UnitDefinition":
        value = {"version": UNIT_VERSION, "key": key, "profile_kind": kind}
        value.update(_plain_builtin(profile, kind))
        return cls(value)


class UnitEditor:
    """A 1280x720-oriented controller; usable with any pygame Surface size."""

    def __init__(self, builtins: Mapping[str, tuple[str, Any]] | None = None,
                 store: UserContentStore | None = None, tr=widgets.IDENTITY_TR):
        self.tr = tr
        self.store = store or UserContentStore()
        self.builtins = (dict(builtins or {}) if builtins is None or isinstance(builtins, Mapping)
                         else catalog_builtins(builtins))
        self.records: list[ContentRecord] = []
        self.listbox = widgets.ListBox()
        self.mode = "browser"
        self.current: UnitDefinition | None = None
        self.status = ""
        self.fields = widgets.FieldList()
        self.kind_box = widgets.ListBox(PROFILE_KINDS)
        self._rects: dict[str, pygame.Rect] = {}
        self._delete_pending = False
        self.path_action: str | None = None
        self.path_input = widgets.TextField(maximum=1024)
        self.refresh()

    def refresh(self) -> None:
        builtin = [ContentRecord(key, "unit", _plain_builtin(value, kind), True)
                   for key, (kind, value) in sorted(self.builtins.items())]
        self.records = builtin + self.store.list("unit")
        self.listbox.set_items([f"{'[built-in]' if item.builtin else '[user]'} {item.key}"
                                for item in self.records])

    @property
    def selected(self) -> ContentRecord | None:
        return self.records[self.listbox.selected] if self.records else None

    def new(self, kind: str, key: str) -> UnitDefinition:
        self.current = UnitDefinition(default_unit(kind, key)); self.mode = "editor"
        self._sync_fields()
        return self.current

    def set_value(self, path: str, value: Any) -> None:
        if self.current is None:
            raise ValueError("no open profile")
        self.current.set_value(path, value)

    def open_selected(self) -> UnitDefinition | None:
        record = self.selected
        if record is None:
            return None
        if record.builtin:
            kind, profile = self.builtins[record.key]
            self.current = UnitDefinition.clone_builtin(profile, kind, "user.clone")
            self.status = self.tr("editor.read_only_clone")
        else:
            self.current = UnitDefinition(record.data)
        self.mode = "editor"
        self._sync_fields()
        return self.current

    def clone_selected(self, key: str) -> UnitDefinition:
        record = self.selected
        if record is None:
            raise ValueError("no selected profile")
        if record.builtin:
            kind, profile = self.builtins[record.key]
            self.current = UnitDefinition.clone_builtin(profile, kind, key)
        else:
            self.current = UnitDefinition(record.data).clone(key)
        self.mode = "editor"
        self._sync_fields()
        return self.current

    def save(self) -> Path:
        if self.current is None:
            raise ValueError("no open profile")
        problems = self.current.validate()
        if problems:
            raise ContentValidationError(problems)
        path = self.store.save("unit", self.current.data)
        self.status = self.tr("editor.saved")
        self.refresh()
        return path

    def export_bundle(self, path: str | Path, *, include_all: bool = False) -> Path:
        if include_all:
            units = [record.data for record in self.store.list("unit")]
        elif self.current is not None:
            units = [self.current.to_dict()]
        else:
            units = []
        return self.store.export_bundle(path, units=units)

    def import_bundle(self, path: str | Path, *, overwrite: bool = False) -> list[ContentRecord]:
        records = self.store.import_bundle(path, overwrite=overwrite)
        self.refresh()
        return records

    def _sync_fields(self) -> None:
        self.fields.set_rows(widgets.mapping_rows(self.current.data) if self.current else ())

    def _begin_path(self, action: str) -> None:
        self.path_action = action
        self.path_input.value = str(self.store.root / "editor-bundle.json")
        self.path_input.selected_all = True
        self.status = self.tr("editor.enter_bundle_path")

    def _handle_path(self, event: pygame.event.Event) -> bool:
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

    def _delete_selected(self) -> None:
        record = self.selected
        if record is not None and not record.builtin:
            self.store.delete("unit", record.key)
            self.status = self.tr("editor.deleted")
            self.refresh()
        self._delete_pending = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            key = pygame.K_UP if y > 0 else pygame.K_DOWN if y < 0 else pygame.K_LEFT if x < 0 else pygame.K_RIGHT
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="")
        if self.path_action:
            return self._handle_path(event)
        if self._delete_pending:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_DELETE):
                self._delete_selected(); return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._delete_pending = False; self.status = ""; return True
            return True
        if self.mode == "kind":
            changed = self.kind_box.handle_event(event, self._rects.get("kinds", pygame.Rect(430, 150, 420, 300)),
                                                 row_height=38)
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                kind = PROFILE_KINDS[self.kind_box.selected]
                self.new(kind, f"user.new_{kind}"); return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.mode = "browser"; return True
            return changed
        if self.mode == "browser":
            changed = self.listbox.handle_event(event, self._rects.get("browser", pygame.Rect(28, 104, 404, 532)))
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.open_selected(); return True
                if event.key == pygame.K_n:
                    self.mode = "kind"; return True
                if event.key == pygame.K_DELETE and self.selected and not self.selected.builtin:
                    if getattr(event, "mod", 0) & pygame.KMOD_SHIFT:
                        self._delete_selected()
                    else:
                        self._delete_pending = True
                        self.status = self.tr("editor.delete_confirm")
                    return True
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
            handled = self.fields.handle_event(event, self._rects.get("fields", pygame.Rect(400, 105, 840, 520)))
            if self.fields.error:
                self.status = self.fields.error
            elif handled:
                self._sync_fields()
            return handled
        if self.fields.handle_event(event, self._rects.get("fields", pygame.Rect(400, 105, 840, 520))):
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.mode = "browser"; return True
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
        # Keep profile-authored values out of translation/template parsing,
        # even when Game has installed an ambient translation scope.
        with translation_scope(None):
            self._draw(surface)

    def _draw(self, surface: pygame.Surface) -> None:
        bounds = surface.get_rect()
        surface.fill(widgets.PALETTE.background)
        widgets.draw_text(surface, self.tr("editor.unit_title"),
                          (20, 15, bounds.width - 40, 42), size=24, bold=True)
        footer = pygame.Rect(0, max(0, bounds.height - 42), bounds.width, min(42, bounds.height))
        content = pygame.Rect(20, 66, max(1, bounds.width - 40), max(1, footer.y - 76))
        with widgets.clipped(surface, content):
            if self.mode == "browser":
                left = pygame.Rect(content.x, content.y, min(420, content.width), content.height)
                inner = widgets.panel(surface, left, "editor.profiles", tr=self.tr)
                self._rects["browser"] = inner
                self.listbox.draw(surface, inner)
                right = pygame.Rect(left.right + 12, content.y,
                                    max(1, content.right - left.right - 12), content.height)
                detail = widgets.panel(surface, right, "editor.selection", tr=self.tr)
                record = self.selected
                if record:
                    lines = [record.key,
                             self.tr("editor.read_only" if record.read_only else "editor.user_content"),
                             self.tr("editor.open_clone"), self.tr("editor.runtime_no")]
                    for row, line in enumerate(lines):
                        widgets.draw_text(surface, raw_text(line) if row == 0 else line,
                                          (detail.x, detail.y + row * 28, detail.width, 25),
                                           color=widgets.PALETTE.dim if row else widgets.PALETTE.text)
            elif self.mode == "kind":
                chooser = pygame.Rect(content.centerx - min(260, content.width // 2), content.y + 35,
                                      min(520, content.width), min(300, content.height - 50))
                inner = widgets.panel(surface, chooser, "editor.choose_kind", tr=self.tr)
                self._rects["kinds"] = inner
                self.kind_box.draw(
                    surface, inner,
                    tr=lambda value: display_value("profile_kind", value, self.tr),
                    row_height=38)
            elif self.current:
                self._sync_fields()
                left_w = min(360, content.width // 3)
                nav = widgets.panel(surface, (content.x, content.y, left_w, content.height),
                                     "field.profile", tr=self.tr)
                lines = (self.current.data.get("key", ""),
                         self.current.data.get("profile_kind", ""),
                         self.current.data.get("name", ""),
                         self.tr("editor.supported_no"))
                for row, line in enumerate(lines):
                    widgets.draw_text(surface, raw_text(line) if row < 3 else line,
                                      (nav.x, nav.y + row * 30, nav.width, 26),
                                      color=widgets.PALETTE.focus if row == 3 else widgets.PALETTE.text,
                                      size=13 if row == 3 else 15)
                detail = widgets.panel(surface,
                    (content.x + left_w + 12, content.y, content.width - left_w - 12, content.height),
                    "editor.validated_fields", tr=self.tr)
                field_rect = pygame.Rect(detail.x, detail.y, detail.width, max(1, detail.height - 32))
                self._rects["fields"] = field_rect
                self.fields.draw(surface, field_rect, tr=self.tr, label_width=260)
                problems = self.current.validate()
                message = (localized_issue(problems[0], self.tr) if problems else
                           self.tr("editor.valid_data"))
                widgets.draw_text(surface, message,
                                  (detail.x, detail.bottom - 29, detail.width, 25),
                                  color=widgets.PALETTE.danger if problems else widgets.PALETTE.focus,
                                  size=13)
        if self.mode == "browser":
            hints = ("editor.select_hint", "editor.open_hint", "editor.new_hint", "editor.remove_hint",
                     "editor.import_hint", "editor.esc_browser")
        elif self.mode == "kind":
            hints = ("editor.select_hint", "editor.create_hint", "editor.cancel_short_hint")
        else:
            hints = ("editor.field_hint", "editor.edit_hint", "editor.save_hint",
                     "editor.bundle_hint", "editor.cancel_hint")
        widgets.draw_footer(surface, footer, hints, tr=self.tr)
        if self.path_action:
            box = pygame.Rect(max(20, bounds.width // 6), bounds.height // 2 - 55,
                              max(1, bounds.width * 2 // 3), 110)
            inner = widgets.panel(surface, box, "editor.bundle_path", tr=self.tr)
            self.path_input.draw(surface, pygame.Rect(inner.x, inner.y + 5, inner.width, 34), focused=True)
        if self.status:
            widgets.draw_text(surface, raw_text(self.status), (bounds.width // 2, 18, bounds.width // 2 - 20, 30),
                              color=widgets.PALETTE.focus, align="right")

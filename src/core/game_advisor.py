"""uConsole overlays of the optional language model.

``F7`` opens the executive officer (situation report, question, typed order,
classification help, station briefing); options page 2 opens the model's
settings, with a second page for its voice (``src/core/game_voice.py``).  Both are administrative overlays: they own input while open and
the simulation keeps running behind them.  Drawing lives in
``src/ui/advisor_view.py``.
"""

from __future__ import annotations

import pygame

from src.core.i18n import message
from src.llm import advisor as advisor_model, client as llm_client, keystore
from src.llm import voice as voice_client
from src.core.preferences import LLM_COACH_LEVELS as LLM_COACH_CYCLE
from src.ui.editor_widgets import TextField

ADVISOR_MODES = ("situation", "question", "order", "classify", "briefing")
TEXT_MODES = ("question", "order")
LLM_ROWS = ("llm_enabled", "llm_url", "llm_model", "llm_key", "llm_radio", "llm_coach",
            "llm_opfor", "test")
VOICE_ROWS = ("tts_enabled", "tts_url", "tts_model", "tts_voice", "tts_key", "tts_xo",
              "tts_crew", "tts_test")
LLM_PAGES = (LLM_ROWS, VOICE_ROWS)
TEXT_ROWS = {"llm_url": llm_client.MAX_URL_LEN, "llm_model": llm_client.MAX_MODEL_LEN,
             "llm_key": keystore.MAX_KEY_LEN, "tts_url": llm_client.MAX_URL_LEN,
             "tts_model": llm_client.MAX_MODEL_LEN, "tts_voice": voice_client.MAX_VOICE_LEN,
             "tts_key": keystore.MAX_KEY_LEN}
KEY_ROWS = ("llm_key", "tts_key")


class AdvisorUiMixin:
    def _init_advisor_ui(self) -> None:
        self.advisor_open = False
        self.advisor_mode = 0
        self.advisor_field = TextField(maximum=advisor_model.MAX_TEXT)
        self.advisor_scroll = None
        self.llm_open = False
        self.llm_sel = 0
        self.llm_page = 0
        self.llm_field = None
        self.llm_field_name = None

    def advisor_mode_name(self) -> str:
        return ADVISOR_MODES[self.advisor_mode % len(ADVISOR_MODES)]

    def advisor_open_proposal(self):
        """The latest unconfirmed typed order of the uConsole, or None."""
        log = self.advisor.log("local")
        entry = log[-1] if log else None
        if (entry is not None and entry["kind"] == "order" and entry["proposal"]
                and not entry["applied"] and not entry.get("discarded")):
            return entry
        return None

    # -- the executive officer (F7) --------------------------------------------

    def _handle_advisor_event(self, e) -> None:
        if e.type == pygame.TEXTINPUT:
            if self.advisor_mode_name() in TEXT_MODES and self.advisor_open_proposal() is None:
                self.advisor_field.handle_text(e.text)
            return
        if e.type != pygame.KEYDOWN:
            return
        key = e.key
        proposal = self.advisor_open_proposal()
        if key == pygame.K_ESCAPE:
            if proposal is not None:
                proposal["discarded"] = True
            elif self.advisor_field.value:
                self.advisor_field.value = ""
            else:
                self.advisor_open = False
            return
        if proposal is not None:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                result = self.advisor_confirm(proposal["seq"])
                self.flash(message("advisor.order_done" if result is True
                                   else "advisor.order_partial"), 3.0)
            elif key == pygame.K_BACKSPACE:
                proposal["discarded"] = True
            return
        if key in (pygame.K_LEFT, pygame.K_RIGHT) and not self.advisor_field.value:
            self.advisor_mode = (self.advisor_mode + (1 if key == pygame.K_RIGHT else -1)) \
                % len(ADVISOR_MODES)
            return
        if (pygame.K_1 <= key <= pygame.K_5 and not self.advisor_field.value
                and self.advisor_mode_name() not in TEXT_MODES):
            self.advisor_mode = key - pygame.K_1
            return
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            step = 6 if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 1
            current = self.advisor_scroll if self.advisor_scroll is not None else 10 ** 6
            self.advisor_scroll = max(0, current + (step if key in (
                pygame.K_DOWN, pygame.K_PAGEDOWN) else -step))
            return
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            mode = self.advisor_mode_name()
            text = self.advisor_field.value.strip() if mode in TEXT_MODES else ""
            if mode in TEXT_MODES and not text:
                return
            result = self.advisor_ask(mode, text)
            if isinstance(result, dict):
                self.advisor_field.value = ""
                self.advisor_scroll = None
            else:
                self.flash(message("advisor.reason." + result), 3.0)
            return
        if self.advisor_mode_name() in TEXT_MODES:
            self.advisor_field.handle_event(e)

    # -- settings (options page 2) -----------------------------------------------

    def _handle_llm_settings_event(self, e) -> None:
        if self.llm_field is not None:
            if e.type == pygame.TEXTINPUT:
                self.llm_field.handle_text(e.text)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.llm_field = self.llm_field_name = None
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._commit_llm_field()
                else:
                    self.llm_field.handle_event(e)
            return
        if e.type != pygame.KEYDOWN:
            return
        key = e.key
        if key == pygame.K_ESCAPE:
            self.llm_open = False
            return
        if key in (pygame.K_TAB, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            self.set_llm_page(self.llm_page + (-1 if key == pygame.K_PAGEUP else 1))
            return
        rows = self.llm_rows()
        if key in (pygame.K_UP, pygame.K_DOWN):
            self.llm_sel = (self.llm_sel + (1 if key == pygame.K_DOWN else -1)) % len(rows)
            return
        if key not in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
            return
        self._activate_llm_row(rows[self.llm_sel % len(rows)],
                               -1 if key == pygame.K_LEFT else 1 if key == pygame.K_RIGHT
                               else 0)

    def llm_rows(self) -> tuple:
        return LLM_PAGES[self.llm_page % len(LLM_PAGES)]

    def set_llm_page(self, page: int) -> None:
        """Language model (0) or its voice (1)."""
        self.llm_page = page % len(LLM_PAGES)
        self.llm_sel = 0
        self.llm_field = self.llm_field_name = None

    def click_llm_row(self, index: int) -> None:
        """A click on a settings row: select it and change it like Right."""
        rows = self.llm_rows()
        if not 0 <= index < len(rows) or self.llm_field_name == rows[index]:
            return
        self.llm_field = self.llm_field_name = None
        self.llm_sel = index
        self._activate_llm_row(rows[index], 1)

    def _activate_llm_row(self, name: str, step: int) -> None:
        """Enter (step 0) or Left/Right (-1/+1) on one settings row."""
        if name == "test":
            self.start_llm_test()
        elif name == "tts_test":
            self.start_voice_test()
        elif name == "tts_voice" and step:
            self.cycle_voice(step)
        elif name in TEXT_ROWS:
            value = "" if name in KEY_ROWS else getattr(self.preferences, name)
            self.llm_field = TextField(value=value, maximum=TEXT_ROWS[name],
                                       secret=name in KEY_ROWS)
            self.llm_field_name = name
        elif name == "llm_coach":
            cycle = LLM_COACH_CYCLE
            step = -1 if step < 0 else 1
            current = self.preferences.llm_coach
            index = cycle.index(current) if current in cycle else 0
            self.set_llm_preference(name, cycle[(index + step) % len(cycle)])
        elif name.startswith("tts_"):
            self.set_voice_preference(name, not getattr(self.preferences, name))
        else:
            self.set_llm_preference(name, not getattr(self.preferences, name))

    def _commit_llm_field(self) -> None:
        name, value = self.llm_field_name, self.llm_field.value.strip()
        self.llm_field = self.llm_field_name = None
        if name in KEY_ROWS:
            saved = self.save_llm_key(value) if name == "llm_key" else self.save_voice_key(value)
            if not saved:
                self.flash(message("llm.key_failed"), 3.0)
            return
        valid = {"llm_url": llm_client.valid_url, "tts_url": llm_client.valid_url,
                 "tts_voice": voice_client.valid_voice}.get(name, llm_client.valid_model)
        if not valid(value):
            self.flash(message("llm.invalid." + name), 3.0)
            return
        if name.startswith("tts_"):
            self.set_voice_preference(name, value)
        else:
            self.set_llm_preference(name, value)

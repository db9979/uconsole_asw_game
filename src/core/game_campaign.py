"""The campaign in the game: menu, leg start, carried state, port call.

``src/core/campaign.py`` holds the campaign and its file; this mixin
starts a leg as an ordinary scenario with the carried torpedo stock,
damage and helicopter, records the result when that mission ends and
offers the port call in the main menu's campaign screen.
"""

from __future__ import annotations

import pygame

from src.core import campaign as campaign_model
from src.core.i18n import message


class CampaignMixin:
    """Campaign menu screen and the link between a leg and its campaign."""

    def _campaign(self):
        if getattr(self, "campaign", None) is None:
            self.campaign = campaign_model.load_campaign()
        return self.campaign

    def new_campaign(self) -> bool:
        self.campaign = campaign_model.CampaignState(self.seed)
        return campaign_model.save_campaign(self.campaign)

    def start_campaign_leg(self) -> bool:
        state = self._campaign()
        if state is None or not state.can_sail():
            return False
        self.scenario_key = state.scenario_key
        self.seed = state.mission_seed()
        self.in_menu = False
        self.main_menu = False
        self.reset(self.seed, state.scenario_key,
                   difficulty_override=state.difficulty_override())
        for name in state.damaged:
            room = self.damage.compartments.get(name)
            if room is not None and room.state == "OK":
                room.state = "BESCHAEDIGT"
        if state.helo_lost:
            self.helo.state = "VERLOREN"
        self.campaign_mission = True
        self.hq_msg(message("campaign.leg_brief", leg=str(state.leg + 1),
                            legs=str(len(campaign_model.LEGS)),
                            reputation=str(state.reputation)))
        return True

    def _campaign_mission_ended(self) -> None:
        """Called once when a mission ends; only a campaign leg counts."""
        if not getattr(self, "campaign_mission", False):
            return
        self.campaign_mission = False
        state = self._campaign()
        if state is None:
            return
        self._campaign_leg_shown = True
        board = getattr(self, "tasking", None)
        counts = board.counts() if board is not None and board.tasks else {}
        state.record(
            won=self.mission_result == "SIEG", ship_sunk=bool(self.damage.ship_sunk),
            score=int(self.score), torpedoes_left=int(self.torpedo_count),
            damaged=[name for name, room in self.damage.compartments.items()
                     if room.state != "OK"],
            helo_lost=self.helo.state == "VERLOREN", incident=bool(self.incident),
            tasks_done=counts.get("done", 0), tasks_failed=counts.get("failed", 0))
        if not campaign_model.save_campaign(state):
            self.flash(message("campaign.save_failed"), 4.0)

    def campaign_end_line(self):
        """End-panel line for a finished campaign leg, else ``None``."""
        state = getattr(self, "campaign", None)
        if state is None or not getattr(self, "_campaign_leg_shown", False):
            return None
        key = {"won": "campaign.end.won", "lost": "campaign.end.lost"}.get(
            state.status, "campaign.end.port")
        return message(key, reputation=str(state.reputation))

    def _handle_campaign_menu_key(self, key: int) -> None:
        state = self._campaign()
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.main_menu = True
            self.main_menu_sel = 2
            return
        confirm = getattr(self, "_campaign_confirm_new", False)
        if key == pygame.K_n and (state is None or state.status != "active" or confirm):
            self._campaign_confirm_new = False
            if not self.new_campaign():
                self.flash(message("campaign.save_failed"), 4.0)
            return
        if key == pygame.K_n:
            # An active campaign is replaced only on a second N.
            self._campaign_confirm_new = True
            return
        self._campaign_confirm_new = False
        if state is None or state.status != "active":
            return
        if state.port and key in (pygame.K_1, pygame.K_2):
            state.call_at_port("refit" if key == pygame.K_1 else "quick")
            if not campaign_model.save_campaign(state):
                self.flash(message("campaign.save_failed"), 4.0)
            return
        if not state.port and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.local_side = "frigate"
            self.start_campaign_leg()

    def _draw_campaign_menu(self, center) -> None:
        from src.core import config
        from src.ui import layout
        state = self._campaign()
        center(self.tr("campaign.title"), 150, color=config.COLOR_WARN)
        lines = []
        if state is None:
            lines.append(("campaign.none", config.COLOR_TEXT_DIM))
        else:
            lines.append((message("campaign.progress", leg=str(state.leg + 1),
                                  legs=str(len(campaign_model.LEGS)),
                                  scenario=self.tr("campaign.scenario." + state.scenario_key)),
                          config.COLOR_TEXT))
            lines.append((message("campaign.standing", reputation=str(state.reputation),
                                  torpedoes=str(state.torpedoes)), config.COLOR_TEXT))
            lines.append((message("campaign.condition",
                                  damaged=str(len(state.damaged)),
                                  helo=self.tr("campaign.helo_lost" if state.helo_lost
                                               else "campaign.helo_ready")),
                          config.COLOR_TEXT_DIM))
            results = " ".join(self.tr("campaign.result." + row["result"])
                               for row in state.history)
            if results:
                lines.append((message("campaign.history", results=results),
                              config.COLOR_TEXT_DIM))
            if state.status == "won":
                lines.append(("campaign.status_won", config.COLOR_OK))
            elif state.status == "lost":
                lines.append(("campaign.status_lost", config.COLOR_DANGER))
            elif state.port:
                issue = campaign_model.resupply(state.reputation)
                lines.append((message("campaign.port_refit", torpedoes=str(
                    max(state.torpedoes, issue))), config.COLOR_WARN))
                lines.append((message("campaign.port_quick", torpedoes=str(min(
                    campaign_model.TORPEDOES_MAX, state.torpedoes + issue // 2))),
                    config.COLOR_WARN))
            else:
                lines.append(("campaign.sail_hint", config.COLOR_OK))
        for index, (text, color) in enumerate(lines):
            layout.blit_line(self.screen, text, (config.SCREEN_W // 2 - 460, 210 + index * 36,
                                                 920, 30), color, size=20, align="center")
        hint = ("campaign.confirm_new" if getattr(self, "_campaign_confirm_new", False)
                else "campaign.menu_hint")
        center(self.tr(hint), 540, color=config.COLOR_TEXT_DIM)

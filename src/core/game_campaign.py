"""The campaigns in the game: menu, leg start, carried state, port call.

``src/core/campaign.py`` holds the frigate's campaign and
``src/core/boat_campaign.py`` the boat's, each in its own file; this mixin
starts a leg as an ordinary scenario with the carried state (the frigate's
torpedo stock, damage and helicopter; the boat's torpedoes and hull
damage), records the result when that mission ends and offers the port
call in the main menu's campaign screen (``Tab`` switches frigate/boat).
"""

from __future__ import annotations

import pygame

from src.core import boat_campaign, campaign as campaign_model
from src.core.i18n import message


class CampaignMixin:
    """Campaign menu screen and the link between a leg and its campaign."""

    def _campaign(self):
        if getattr(self, "campaign", None) is None:
            self.campaign = campaign_model.load_campaign()
        return self.campaign

    def _boat_campaign(self):
        if getattr(self, "boat_campaign", None) is None:
            self.boat_campaign = boat_campaign.load_campaign()
        return self.boat_campaign

    def _menu_campaign(self):
        """The campaign the campaign screen shows: the frigate's or the boat's."""
        return (self._boat_campaign() if getattr(self, "campaign_side", "frigate") == "boat"
                else self._campaign())

    def new_campaign(self) -> bool:
        self.campaign = campaign_model.CampaignState(self.seed)
        return campaign_model.save_campaign(self.campaign)

    def new_boat_campaign(self) -> bool:
        self.boat_campaign = boat_campaign.BoatCampaignState(self.seed)
        return boat_campaign.save_campaign(self.boat_campaign)

    def start_boat_campaign_leg(self) -> bool:
        state = self._boat_campaign()
        if state is None or not state.can_sail():
            return False
        self.local_side = "uboot"
        self.scenario_key = state.scenario_key
        self.seed = state.mission_seed()
        self.in_menu = False
        self.main_menu = False
        self.reset(self.seed, state.scenario_key)
        boat = self.claim_opfor_sub()
        if boat is not None:
            boat_campaign.put_aboard(boat.sub, state)
        self.campaign_mission = True
        self.campaign_mission_side = "boat"
        return True

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
        self.campaign_mission_side = "frigate"
        self.hq_msg(message("campaign.leg_brief", leg=str(state.leg + 1),
                            legs=str(len(campaign_model.LEGS)),
                            reputation=str(state.reputation)))
        return True

    def _campaign_mission_ended(self) -> None:
        """Called once when a mission ends; only a campaign leg counts."""
        if not getattr(self, "campaign_mission", False):
            return
        self.campaign_mission = False
        if getattr(self, "campaign_mission_side", "frigate") == "boat":
            self._boat_campaign_leg_ended()
            return
        state = self._campaign()
        if state is None:
            return
        self._campaign_leg_shown = True
        self._campaign_leg_side = "frigate"
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

    def _boat_campaign_leg_ended(self) -> None:
        from src.core import boat_debrief, boat_missions
        state = self._boat_campaign()
        if state is None:
            return
        self._campaign_leg_shown = True
        self._campaign_leg_side = "boat"
        boat = self._opfor
        sub = boat.sub if boat is not None else boat_missions.target_sub(self)
        state.record(
            won=boat_debrief.outcome(self, boat) in boat_campaign.WINS,
            boat_sunk=sub is None or sub.sunk or sub.state == "SINKING",
            torpedoes_left=int(sub.torpedoes_left) if sub is not None else 0,
            damage=float(sub.damage) if sub is not None else 100.0)
        if not boat_campaign.save_campaign(state):
            self.flash(message("campaign.save_failed"), 4.0)

    def campaign_end_line(self):
        """End-panel line for a finished campaign leg, else ``None``."""
        state = (getattr(self, "boat_campaign", None)
                 if getattr(self, "_campaign_leg_side", "frigate") == "boat"
                 else getattr(self, "campaign", None))
        if state is None or not getattr(self, "_campaign_leg_shown", False):
            return None
        key = {"won": "campaign.end.won", "lost": "campaign.end.lost"}.get(
            state.status, "campaign.end.port")
        return message(key, reputation=str(state.reputation))

    def _handle_campaign_menu_key(self, key: int) -> None:
        boat_side = getattr(self, "campaign_side", "frigate") == "boat"
        state = self._menu_campaign()
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.main_menu = True
            self.main_menu_sel = self.main_menu_index("campaign")
            return
        if key == pygame.K_TAB:
            self.campaign_side = "frigate" if boat_side else "boat"
            self._campaign_confirm_new = False
            return
        if key in (pygame.K_UP, pygame.K_DOWN):
            self.menu_sel = 1 - min(1, max(0, self.menu_sel))
            return
        if key in (pygame.K_LEFT, pygame.K_RIGHT):
            # Weather and time of the next leg.
            self.cycle_start_choice(("weather", "time")[min(1, max(0, self.menu_sel))],
                                    1 if key == pygame.K_RIGHT else -1)
            return
        confirm = getattr(self, "_campaign_confirm_new", False)
        if key == pygame.K_n and (state is None or state.status != "active" or confirm):
            self._campaign_confirm_new = False
            if not (self.new_boat_campaign() if boat_side else self.new_campaign()):
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
            saved = (boat_campaign.save_campaign(state) if boat_side
                     else campaign_model.save_campaign(state))
            if not saved:
                self.flash(message("campaign.save_failed"), 4.0)
            return
        if not state.port and key in (pygame.K_RETURN, pygame.K_SPACE):
            if boat_side:
                self.start_boat_campaign_leg()
            else:
                self.local_side = "frigate"
                self.start_campaign_leg()

    def _draw_campaign_menu(self, center) -> None:
        from src.core import config
        from src.ui import layout
        boat_side = getattr(self, "campaign_side", "frigate") == "boat"
        state = self._menu_campaign()
        center(self.tr("campaign.boat.title" if boat_side else "campaign.title"), 150,
               color=config.COLOR_WARN)
        lines = []
        if state is None:
            lines.append(("campaign.boat.none" if boat_side else "campaign.none",
                          config.COLOR_TEXT_DIM))
        elif boat_side:
            lines = self._boat_campaign_lines(state)
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
        if state is not None and state.status == "active" and not state.port:
            self._draw_start_choices(center, 478, config.SCREEN_W // 2)
        hint = ("campaign.confirm_new" if getattr(self, "_campaign_confirm_new", False)
                else "campaign.menu_hint")
        center(self.tr(hint), 540, color=config.COLOR_TEXT_DIM,
               keys=("Enter", None, "N", "Tab", "Esc") if hint == "campaign.menu_hint"
               else None)

    def _boat_campaign_lines(self, state) -> list:
        from src.core import config
        torpedoes = (self.tr("campaign.boat.full_load") if state.torpedoes is None
                     else str(state.torpedoes))
        lines = [
            (message("campaign.progress", leg=str(state.leg + 1),
                     legs=str(len(boat_campaign.LEGS)),
                     scenario=self.tr("scenario." + config.SCENARIO_NAMES[state.scenario_key]
                                      + ".title")), config.COLOR_TEXT),
            (message("campaign.boat.standing", reputation=str(state.reputation),
                     torpedoes=torpedoes), config.COLOR_TEXT),
            (message("campaign.boat.condition", damage=str(state.damage)),
             config.COLOR_TEXT_DIM),
        ]
        results = " ".join(self.tr("campaign.result." + row["result"])
                           for row in state.history)
        if results:
            lines.append((message("campaign.history", results=results), config.COLOR_TEXT_DIM))
        if state.status == "won":
            lines.append(("campaign.status_won", config.COLOR_OK))
        elif state.status == "lost":
            lines.append(("campaign.boat.status_lost", config.COLOR_DANGER))
        elif state.port:
            quick = state.quick_load()
            lines.append(("campaign.boat.port_refit", config.COLOR_WARN))
            lines.append((message("campaign.boat.port_quick", torpedoes=(
                self.tr("campaign.boat.full_load") if quick is None else str(quick)),
                damage=str(state.damage)), config.COLOR_WARN))
        else:
            lines.append(("campaign.boat.sail_hint", config.COLOR_OK))
        return lines

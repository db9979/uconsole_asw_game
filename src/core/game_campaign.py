"""The campaigns in the game: theatre map, hotspot briefing, carried state, port.

``src/core/campaign.py`` holds the frigate's campaign and
``src/core/boat_campaign.py`` the boat's, each in its own file, and
``src/core/theatre.py`` their common front situation and hotspots.  This
mixin draws the campaign screen (the sector map with the open hotspots, the
situation, the carried state and the port call; ``Tab`` switches
frigate/boat), opens a hotspot's briefing, starts its mission as an
ordinary scenario with the carried state (the frigate's torpedo stock,
damage and helicopter; the boat's torpedoes and hull damage) and records
the result when that mission ends.
"""

from __future__ import annotations

import pygame

from src.core import boat_campaign, campaign as campaign_model, config, theatre
from src.core.i18n import message, raw_text
from src.ui import layout, pointer
from src.ui.splash_view import draw_menu_panel

MAP_RECT = (60, 172, 380, 380)
PANEL_RECT = (478, 166, 754, 414)
PANEL_X, PANEL_W = 490, 730
ROW_TOP, ROW_H = 300, 28
ROLE_COLORS = {"patrol": config.COLOR_OK, "strike": config.COLOR_DANGER,
               "defence": config.COLOR_WARN, "decisive": config.COLOR_CONTACT}


def _lage_color(lage: int):
    if lage < theatre.BAND_LOW:
        return config.COLOR_DANGER
    return config.COLOR_WARN if lage < theatre.BAND_HIGH else config.COLOR_OK


class CampaignMixin:
    """Campaign screen and the link between a mission and its campaign."""

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
        self.campaign_hotspot_sel = 0
        return campaign_model.save_campaign(self.campaign)

    def new_boat_campaign(self) -> bool:
        self.boat_campaign = boat_campaign.BoatCampaignState(self.seed)
        self.campaign_hotspot_sel = 0
        return boat_campaign.save_campaign(self.boat_campaign)

    def _selected_hotspot(self, state):
        """The hotspot under the campaign screen's cursor (or ``None``)."""
        if state is None:
            return None
        spots = state.theatre.ordered()
        if not spots:
            return None
        index = min(len(spots) - 1, max(0, getattr(self, "campaign_hotspot_sel", 0)))
        return spots[index]

    def _hotspot_id(self, state, hotspot_id):
        if hotspot_id is None:
            spot = self._selected_hotspot(state)
            return None if spot is None else spot["id"]
        return hotspot_id

    # --- starting a mission ---------------------------------------------------------

    def start_boat_campaign_leg(self, hotspot_id: int | None = None) -> bool:
        state = self._boat_campaign()
        hotspot_id = self._hotspot_id(state, hotspot_id)
        if state is None or not state.can_sail() or state.scenario_of(hotspot_id) is None:
            return False
        scenario = state.scenario_of(hotspot_id)
        self.local_side = "uboot"
        self.scenario_key = scenario
        self.seed = state.mission_seed()
        self.in_menu = False
        self.main_menu = False
        self._campaign_briefing = None
        self.reset(self.seed, scenario)
        boat = self.claim_opfor_sub()
        if boat is not None:
            boat_campaign.put_aboard(boat.sub, state)
        self.campaign_mission = True
        self.campaign_mission_side = "boat"
        self.campaign_hotspot = hotspot_id
        return True

    def start_campaign_leg(self, hotspot_id: int | None = None) -> bool:
        state = self._campaign()
        hotspot_id = self._hotspot_id(state, hotspot_id)
        if state is None or not state.can_sail() or state.scenario_of(hotspot_id) is None:
            return False
        scenario = state.scenario_of(hotspot_id)
        self.scenario_key = scenario
        self.seed = state.mission_seed()
        self.in_menu = False
        self.main_menu = False
        self._campaign_briefing = None
        self.reset(self.seed, scenario, difficulty_override=state.difficulty_override())
        for name in state.damaged:
            room = self.damage.compartments.get(name)
            if room is not None and room.state == "OK":
                room.state = "BESCHAEDIGT"
        if state.helo_lost:
            self.helo.state = "VERLOREN"
        self.campaign_mission = True
        self.campaign_mission_side = "frigate"
        self.campaign_hotspot = hotspot_id
        self.hq_msg(message("campaign.hotspot_brief",
                            name=state.theatre.name(state.theatre.hotspot(hotspot_id)),
                            mission=str(state.missions + 1),
                            lage=str(state.theatre.lage),
                            reputation=str(state.reputation)))
        return True

    # --- a mission's result ---------------------------------------------------------

    def _campaign_mission_ended(self) -> None:
        """Called once when a mission ends; only a campaign mission counts."""
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
            getattr(self, "campaign_hotspot", None),
            won=self.mission_result == "SIEG", ship_sunk=bool(self.damage.ship_sunk),
            score=int(self.score), torpedoes_left=int(self.torpedo_count),
            damaged=[name for name, room in self.damage.compartments.items()
                     if room.state != "OK"],
            helo_lost=self.helo.state == "VERLOREN", incident=bool(self.incident),
            tasks_done=counts.get("done", 0), tasks_failed=counts.get("failed", 0),
            enemy_sunk=sum(1 for sub in self.subs
                           if sub.side == "hostile" and sub.sunk))
        self.campaign_hotspot_sel = 0
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
        outcome = boat_debrief.outcome(self, boat)
        state.record(
            getattr(self, "campaign_hotspot", None),
            won=outcome in boat_campaign.WINS,
            boat_sunk=sub is None or sub.sunk or sub.state == "SINKING",
            torpedoes_left=int(sub.torpedoes_left) if sub is not None else 0,
            damage=float(sub.damage) if sub is not None else 100.0,
            enemy_sunk=(int(bool(self.damage.ship_sunk))
                        + int(outcome in boat_campaign.ENEMY_SHIP_SUNK)))
        self.campaign_hotspot_sel = 0
        if not boat_campaign.save_campaign(state):
            self.flash(message("campaign.save_failed"), 4.0)

    def campaign_end_line(self):
        """End-panel line for a finished campaign mission, else ``None``."""
        state = (getattr(self, "boat_campaign", None)
                 if getattr(self, "_campaign_leg_side", "frigate") == "boat"
                 else getattr(self, "campaign", None))
        if state is None or not getattr(self, "_campaign_leg_shown", False):
            return None
        if state.status == "active":
            return message("campaign.end.port", lage=str(state.theatre.lage),
                           reputation=str(state.reputation))
        return message("campaign.end.over",
                       outcome=message("campaign.outcome." + state.outcome),
                       lage=str(state.theatre.lage))

    # --- keys -------------------------------------------------------------------------

    def _handle_campaign_menu_key(self, key: int) -> None:
        boat_side = getattr(self, "campaign_side", "frigate") == "boat"
        state = self._menu_campaign()
        if getattr(self, "_campaign_briefing", None) is not None:
            self._handle_campaign_briefing_key(key, state, boat_side)
            return
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.main_menu = True
            self.main_menu_sel = self.main_menu_index("campaign")
            return
        if key == pygame.K_TAB:
            self.campaign_side = "frigate" if boat_side else "boat"
            self._campaign_confirm_new = False
            self.campaign_hotspot_sel = 0
            return
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            count = len(state.theatre.hotspots) if state is not None else 0
            if count:
                step = -1 if key in (pygame.K_UP, pygame.K_LEFT) else 1
                current = min(count - 1, max(0, getattr(self, "campaign_hotspot_sel", 0)))
                self.campaign_hotspot_sel = (current + step) % count
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
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            spot = self._selected_hotspot(state)
            if state.port:
                self.flash(message("campaign.port_first"), 2.5)
            elif spot is not None:
                # The hotspot's briefing: weather, time and length, then sail.
                self._campaign_briefing = spot["id"]
                self.scenario_key = spot["scenario"]
                self.menu_sel = 0

    def _handle_campaign_briefing_key(self, key: int, state, boat_side: bool) -> None:
        hotspot_id = self._campaign_briefing
        if state is None or state.scenario_of(hotspot_id) is None or not state.can_sail():
            self._campaign_briefing = None
            return
        rows = self.start_choice_rows()
        if key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
            self._campaign_briefing = None
        elif key in (pygame.K_UP, pygame.K_DOWN):
            self.menu_sel = (min(len(rows) - 1, max(0, self.menu_sel))
                             + (1 if key == pygame.K_DOWN else -1)) % len(rows)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.cycle_start_choice(rows[min(len(rows) - 1, max(0, self.menu_sel))],
                                    1 if key == pygame.K_RIGHT else -1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if boat_side:
                self.start_boat_campaign_leg(hotspot_id)
            else:
                self.local_side = "frigate"
                self.start_campaign_leg(hotspot_id)

    def _click_hotspot(self, index: int) -> None:
        """A click on a hotspot (row or marker): select it; on the selected
        one, open its briefing (as Enter)."""
        if getattr(self, "campaign_hotspot_sel", 0) == index:
            self._click_menu_row(lambda: None)
        else:
            self.campaign_hotspot_sel = index

    # --- drawing ------------------------------------------------------------------------

    def _draw_campaign_menu(self, center) -> None:
        boat_side = getattr(self, "campaign_side", "frigate") == "boat"
        state = self._menu_campaign()
        if state is not None and getattr(self, "_campaign_briefing", None) is not None \
                and state.scenario_of(self._campaign_briefing) is not None:
            self._draw_campaign_briefing(center, state)
            return
        self._campaign_briefing = None
        center(self.tr("campaign.boat.title" if boat_side else "campaign.title"), 150,
               color=config.COLOR_WARN)
        if state is None:
            layout.blit_line(self.screen, "campaign.boat.none" if boat_side
                             else "campaign.none",
                             (config.SCREEN_W // 2 - 460, 300, 920, 30),
                             config.COLOR_TEXT_DIM, size=20, align="center")
        else:
            self._draw_campaign_map(state)
            self._draw_campaign_panel(state, boat_side)
        hint = ("campaign.confirm_new" if getattr(self, "_campaign_confirm_new", False)
                else "campaign.menu_hint")
        center(self.tr(hint), 600, color=config.COLOR_TEXT_DIM,
               keys=("Enter", None, None, "N", "Tab", "Esc")
               if hint == "campaign.menu_hint" else None)

    def _campaign_map_surface(self, state):
        """The sector's land at map scale, cached per world and sector."""
        fixed = self.world_mode == "fixed"
        key = (fixed, state.base_seed % 128, MAP_RECT[2], MAP_RECT[3])
        cached = getattr(self, "_campaign_map_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1], cached[2]
        from src.world.coastline import Coastline
        from src.world.real_coast import sector_for_seed
        if fixed:
            lands = [land.points for land in Coastline.load().landmasses]
            label = message("menu.fixed_chart")
        else:
            sector, _ = sector_for_seed(state.base_seed)
            lands = [land["points"] for land in sector["landmasses"]]
            label = raw_text(sector["name"])
        surface = pygame.Surface(MAP_RECT[2:])
        surface.fill(config.COLOR_GEO_BG)
        scale = MAP_RECT[2] / theatre.MAP_NM
        for step in range(1, 5):
            at = round(step * MAP_RECT[2] / 5)
            pygame.draw.line(surface, config.COLOR_GEO_GRID, (at, 0), (at, MAP_RECT[3]), 1)
            pygame.draw.line(surface, config.COLOR_GEO_GRID, (0, at), (MAP_RECT[2], at), 1)
        for points in lands:
            poly = [(x * scale, y * scale) for x, y in points]
            if len(poly) >= 3:
                pygame.draw.polygon(surface, config.COLOR_LAND, poly)
                pygame.draw.lines(surface, config.COLOR_LAND_EDGE, True, poly, 1)
        self._campaign_map_cache = (key, surface, label)
        return surface, label

    def _draw_campaign_map(self, state) -> None:
        s = self.screen
        x0, y0, w, h = MAP_RECT
        surface, label = self._campaign_map_surface(state)
        s.blit(surface, (x0, y0))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, MAP_RECT, 1)
        layout.corner_brackets(s, MAP_RECT)
        layout.blit_line(s, message("campaign.map_sector", sector=label),
                         (x0, y0 + h + 3, w, 20), config.COLOR_TEXT_DIM, size=14)
        scale = w / theatre.MAP_NM
        selected = self._selected_hotspot(state)
        for index, spot in enumerate(state.theatre.ordered()):
            px, py = x0 + round(spot["x"] * scale), y0 + round(spot["y"] * scale)
            color = ROLE_COLORS[state.theatre.role(spot)]
            chosen = selected is not None and spot["id"] == selected["id"]
            pygame.draw.circle(s, color, (px, py), 7 if chosen else 5)
            pygame.draw.circle(s, color, (px, py), 13 if chosen else 9, 1)
            if state.theatre.role(spot) == "decisive":
                pygame.draw.circle(s, color, (px, py), 17, 1)
            label_x = px + 18 if px < x0 + w - 140 else px - 138
            layout.blit_line(s, raw_text(state.theatre.name(spot)),
                             (label_x, py - 10, 120, 20),
                             config.COLOR_TEXT if chosen else config.COLOR_TEXT_DIM,
                             size=14, align="left" if label_x > px else "right")
            if state.status == "active":
                pointer.add_action((px - 14, py - 14, 28, 28),
                                   lambda _pos, i=index: self._click_hotspot(i))

    def _draw_campaign_panel(self, state, boat_side: bool) -> None:
        s = self.screen
        x, w = PANEL_X, PANEL_W
        front = state.theatre
        draw_menu_panel(s, PANEL_RECT, (PANEL_X, 166, 0, 0))
        layout.gauge(s, (x, 172, w, layout.line_pitch(18, 0) + 10), front.lage / 100.0,
                     label=message("campaign.lage_label"),
                     value=message("campaign.lage_value", lage=str(front.lage)),
                     color=_lage_color(front.lage), size=18, bar_h=8)
        layout.blit_line(s, message("campaign.forces", enemy=str(front.enemy),
                                    enemy_max=str(theatre.ENEMY_START),
                                    losses=str(front.losses),
                                    losses_max=str(theatre.LOSSES_MAX),
                                    mission=str(state.missions),
                                    missions_max=str(theatre.MISSIONS_MAX)),
                         (x, 210, w, 26), config.COLOR_TEXT, size=18)
        for index, (text, color) in enumerate(self._campaign_carried_lines(state,
                                                                           boat_side)):
            layout.blit_line(s, text, (x, 238 + index * 26, w, 26), color, size=18)
        if state.status != "active":
            self._draw_campaign_summary(state, x, w)
            return
        selected = self._selected_hotspot(state)
        for index, spot in enumerate(front.ordered()):
            y = ROW_TOP + index * ROW_H
            chosen = selected is not None and spot["id"] == selected["id"]
            if chosen:
                pygame.draw.rect(s, config.COLOR_SELECT_BG, (x - 6, y, w + 12, ROW_H - 2))
            role = front.role(spot)
            pygame.draw.circle(s, ROLE_COLORS[role], (x + 8, y + ROW_H // 2 - 1), 5)
            layout.blit_line(s, message(
                "campaign.hotspot_row", name=raw_text(front.name(spot)),
                scenario=message("scenario." + config.SCENARIO_NAMES[spot["scenario"]]
                                 + ".title"),
                role=message("campaign.role." + role)),
                (x + 22, y + 2, w - 22, ROW_H - 4),
                config.COLOR_TEXT if chosen else config.COLOR_TEXT_DIM, size=18)
            pointer.add_action((x - 6, y, w + 12, ROW_H - 2),
                               lambda _pos, i=index: self._click_hotspot(i))
        y = ROW_TOP + 4 * ROW_H + 4
        if selected is not None:
            layout.blit_block(s, self._stakes_text(front, selected), x, y, w, 44,
                              config.COLOR_TEXT_DIM, size=16)
        y += 50
        if state.port:
            for index, text in enumerate(self._port_lines(state, boat_side)):
                layout.blit_line(s, text, (x, y + index * 26, w, 26), config.COLOR_WARN,
                                 size=18)
                pointer.add_action((x, y + index * 26, w, 26),
                                   lambda _pos, k=(pygame.K_1, pygame.K_2)[index]:
                                   self.handle_event(_key_event(k)))
        else:
            layout.blit_line(s, "campaign.boat.sail_hint" if boat_side
                             else "campaign.sail_hint", (x, y, w, 26), config.COLOR_OK,
                             size=18)
        if state.history:
            results = " ".join(self.tr("campaign.result." + row["result"])
                               for row in state.history)
            layout.blit_block(s, message("campaign.history", results=results),
                              x, ROW_TOP + 4 * ROW_H + 110, w, 44, config.COLOR_TEXT_DIM,
                              size=16)

    def _stakes_text(self, front, spot) -> str:
        role = front.role(spot)
        win, loss = theatre.STAKES[role]
        key = ("campaign.stakes.decisive" if role == "decisive" else
               "campaign.stakes.defence" if role == "defence" else "campaign.stakes")
        waits = theatre.EXPIRE_AFTER - spot["age"]
        return message(key, win=f"+{win}", loss=str(loss), waits=str(waits))

    def _campaign_carried_lines(self, state, boat_side: bool) -> list:
        if boat_side:
            torpedoes = (message("campaign.boat.full_load") if state.torpedoes is None
                         else str(state.torpedoes))
            return [(message("campaign.boat.standing", reputation=str(state.reputation),
                             torpedoes=torpedoes), config.COLOR_TEXT),
                    (message("campaign.boat.condition", damage=str(state.damage)),
                     config.COLOR_TEXT_DIM)]
        return [(message("campaign.standing", reputation=str(state.reputation),
                         torpedoes=str(state.torpedoes)), config.COLOR_TEXT),
                (message("campaign.condition", damaged=str(len(state.damaged)),
                         helo=message("campaign.helo_lost" if state.helo_lost
                                      else "campaign.helo_ready")),
                 config.COLOR_TEXT_DIM)]

    def _port_lines(self, state, boat_side: bool) -> list:
        if boat_side:
            quick = state.quick_load()
            return ["campaign.boat.port_refit",
                    message("campaign.boat.port_quick", torpedoes=(
                        message("campaign.boat.full_load") if quick is None
                        else str(quick)), damage=str(state.damage))]
        return [message("campaign.port_refit", torpedoes=str(state.port_offer("refit"))),
                message("campaign.port_quick", torpedoes=str(state.port_offer("quick")))]

    def _draw_campaign_summary(self, state, x: int, w: int) -> None:
        """The finished campaign: outcome, record and what it came to."""
        s = self.screen
        color = {"won": config.COLOR_OK, "lost": config.COLOR_DANGER}.get(
            state.status, config.COLOR_WARN)
        layout.blit_line(s, message("campaign.outcome." + state.outcome),
                         (x, ROW_TOP, w, 32), color, size=24)
        layout.blit_block(s, message("campaign.outcome_text." + state.outcome),
                          x, ROW_TOP + 38, w, 70, config.COLOR_TEXT, size=18)
        won = sum(1 for row in state.history if row["result"] == "won")
        layout.blit_line(s, message("campaign.summary", missions=str(state.missions),
                                    won=str(won), lost=str(state.missions - won),
                                    lage=str(state.theatre.lage)),
                         (x, ROW_TOP + 116, w, 26), config.COLOR_TEXT, size=18)
        results = " ".join(self.tr("campaign.result." + row["result"])
                           for row in state.history)
        layout.blit_block(s, message("campaign.history", results=results),
                          x, ROW_TOP + 146, w, 52, config.COLOR_TEXT_DIM, size=16)
        layout.blit_line(s, "campaign.new_hint", (x, ROW_TOP + 204, w, 26),
                         config.COLOR_WARN, size=18)

    def _draw_campaign_briefing(self, center, state) -> None:
        """A hotspot's briefing: the scenario's own brief and goal, the stakes
        for the theatre, then weather, time and length as in any briefing."""
        s = self.screen
        cx = config.SCREEN_W // 2
        spot = state.theatre.hotspot(self._campaign_briefing)
        name = config.SCENARIO_NAMES[spot["scenario"]]
        sc = config.SCENARIOS[spot["scenario"]]
        center(message("campaign.briefing_title", name=raw_text(state.theatre.name(spot)),
                       scenario=message("scenario." + name + ".title")), 160,
               self.menu_font_big, config.COLOR_WARN)
        layout.blit_block(s, self.tr("scenario." + name + ".brief"),
                          cx - 420, 196, 840, 172, color=config.COLOR_TEXT, size=20)
        layout.blit_line(s, self._stakes_text(state.theatre, spot),
                         (cx - 420, 376, 840, 24), config.COLOR_WARN, size=18,
                         align="center")
        if sc["win_text"]:
            center(message("menu.goal_value", goal=self.tr("scenario." + name + ".win")),
                   416, color=config.COLOR_OK)
        if sc["lose_text"]:
            center(message("menu.loss_value", loss=self.tr("scenario." + name + ".lose")),
                   442, color=config.COLOR_DANGER)
        self._draw_start_choices(center, 470, cx)
        center(self.tr("campaign.briefing_hint"), 548, color=config.COLOR_TEXT_DIM,
               keys=("Enter", None, "Esc"))


def _key_event(key: int):
    from src.core import pointer_input
    return pointer_input.key_event(key)

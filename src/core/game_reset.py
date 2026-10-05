"""``Game.reset``: build a fresh mission world (start and restart).

Verbatim move from ``game.py`` so that the composition root stays
composition only; ``Game`` gets it from ``ResetMixin``.
"""

import copy
import math
import weakref
from collections import deque

from src.audio.receiver import AcousticReceiver
from src.core import config, mission_modes
from src.core.plot import PlotLayer
from src.core.chart_history import ChartHistory
from src.core.map_fx import MapFx
from src.core.sight_events import SightEvents
from src.core.autocrew import AutocrewController
from src.ship.route import Route
from src.core.i18n import message
from src.core.mission import Mission
from src.core.station import Station
from src.core import optics
from src.core.limits import MAX_AIR_PICTURE_TRACKS
from src.sensors.ais import AISReceiver
from src.sonar import analysis_tools
from src.data.catalog import CATALOG
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.enemies import traffic
from src.sensors.tracks import TrackPicture
from src.sensors.fusion import OPZFusionPicture
from src.sensors.esm import ECMJammer, ESMPicture
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem
from src.sonar.station import SonarStation
from src.ui.feedback import EventFeed
from src.ui import simlog_map
from src.ui.viewport import Viewport
from src.air.helicopter import Helicopter
from src.air.flights import FlightManager
from src.world.world import World
from src.world.coastline import Coastline
from src.weapons import depth_charge
from src.weapons.asw import ConsumableStore, WeaponBattery, ownship_loadout
from src.weapons.air_defense import air_defense_loadout, make_softkill_store


class ResetMixin:
    """The start/restart of a mission world (``reset``)."""

    def reset(self, seed: int, scenario_key: str = None, *, publish_intel: bool = True,
              reference_sector: int | None = None,
              difficulty_override: dict | None = None) -> None:
        """Spielzustand neu aufbauen (Start/Neustart).

        W4: Szenario (config.SCENARIOS) legt Level, Missionstyp und
        Startposition fest. s4_zufall = seed-basiert wie vor dem Refactor.
        """
        import random
        if getattr(self, "_autosave_armed", False):
            # A new mission replaces the one the autosave would continue.
            self.discard_autosave()
        elif hasattr(self, "_autosave_worker"):
            # No queued autosave of the old world may land after the reset.
            self._settle_autosave()
        # The frigate's sonar workstation; ``game.sonar`` & co. delegate to it.
        self._frigate_sonar = SonarStation(kind="frigate")
        self._sonar_ctx = self._frigate_sonar
        # A crewed hostile submarine (save v15 ``crew``); the hold keeps a
        # loaded binding until its crew returns or the AI takes the boat back.
        self._opfor = None
        self._opfor_hold_s = 0.0
        self.runtime_catalog = CATALOG
        self.commander_open = False
        self.audio.stop()
        self._frame_clock_reset = True
        self._sound_events.clear()
        self.callouts.clear()
        self.callouts.spoken = self.callouts.seq
        self.speaker.stop()
        self.voice_stop()
        self._ping_pulses.clear()
        self._ping_intercepts.clear()
        self._sonar_audio_sequence = -1
        scenario_key = scenario_key or self.scenario_key
        if scenario_key not in config.SCENARIOS:
            scenario_key = "s4_zufall"
        sc = config.SCENARIOS[scenario_key]
        self.scenario_key = scenario_key
        self.difficulty = {**config.DEFAULT_DIFFICULTY,
                           **(sc["difficulty"] if sc["difficulty"] is not None
                              else self.menu_difficulty),
                           # A campaign leg brings its carried torpedo stock.
                           **(difficulty_override or {})}
        # The realism level of this mission (preference, saved per mission).
        self.level = self._preferred_level()
        self._difficulty_base = tuple(self.difficulty[name]
                                      for name in config.DIFFICULTY_FIELD_ORDER)
        self.difficulty = config.apply_level(self.difficulty, self.level)

        if reference_sector is not None:
            # A mission's reference world: the named real sector, not seed % 128.
            self.world_mode = "real_fixed"
            coast = Coastline.generate(seed, sector_index=reference_sector)
        else:
            coast = Coastline.load() if self.world_mode == "fixed" else None
        self.world = World(seed=seed, coast=coast)
        if sc["difficulty"] is None:
            self.world.sea_state = int(self.difficulty["sea_state_start"])
            self.world.refresh_weather()
        self._apply_start_environment()
        start = sc["ship_start"] or (250.0, 250.0)
        course = sc["ship_course"]
        if course is None:
            course = 90.0
        from src.core import boat_missions
        short = (getattr(self, "start_length", "normal") == "short"
                 and "short_time_limit_s" in config.MISSION_TYPES.get(
                     sc["mission_type"], {}))
        placed = boat_missions.frigate_start(self.world, scenario_key, seed, short)
        if placed is not None:
            # Scenarios 8 to 20: the strait's gate, the coast section, the
            # supply ship's beam, the datum, the tanker's quarter ...
            # (src/core/mission_geo.py, src/core/mission_modes.py).
            start, course = placed[:2], placed[2]
        sx, sy = self.world.nearest_safe_hull(start[0], start[1], course)
        if placed is None:
            # A patrol start that the real coast puts in a loch moves out.
            sx, sy = self.world.open_water_start(sx, sy, course)
        self.ship = Ship(x_nm=sx, y_nm=sy, course_deg=course)
        self.live_traffic.configure(self, self.world, self.preferences)
        self.sonar = SonarSystem(
            seed=seed, acoustic_profiles=self.runtime_catalog.acoustic_profiles)
        self._last_tow_state = self.sonar.tow_state
        rng = random.Random(seed)
        self.rng_world = rng  # Phase 2: geteilt mit allen Entitäten (Save/Load)
        self.rng_asw = random.Random(seed + 27182)
        self.seed = seed
        self.sim_t = 0.0
        self._sensor_acc = 0.0
        self._esm_acc = 0.0
        self._radio_acc = 0.0
        self._slow_acc = 0.0
        self.simlog = deque(maxlen=config.SIMLOG_MAX_ENTRIES)
        self._simlog_seq = 0
        self._simlog_acc = 0.0
        self.feed = EventFeed(sink=self._record_simlog)

        # M6: Mission (W4: Szenario kann den Typ fixieren)
        self.mission = Mission(seed, type_key=sc["mission_type"],
                               difficulty=self.difficulty)
        if (getattr(self, "start_length", "normal") == "short"
                and self.mission.spec is not None
                and "short_time_limit_s" in self.mission.spec):
            # The short variant: its time limit marks it (save ``mission_runtime``).
            self.mission.time_limit_s = self.mission.spec["short_time_limit_s"]
        self.custom_mission_definition = None
        # Mission unit id -> entity id of the placed unit (custom missions).
        self.mission_units = {}
        # Authored events not yet run, in order of their time (custom missions).
        self.mission_events_pending = []
        self.mission_time = 0.0
        self.score = 0
        # The combat swimmers' lock-out so far (save ``swimmer_hold_s``).
        self.swimmer_hold_s = 0.0
        # The counters of scenarios 13, 19 and 20 (save ``mission_progress``).
        self.mission_progress = mission_modes.new_progress()
        # A free patrol's encounters and points (save ``free_roam``; set up by
        # ``boat_missions.setup`` once the world is populated).
        self.free_roam = None
        # HQ orders and incidents (save ``tasking``); none in custom missions.
        self._reset_tasking()
        # Incidents at sea (save ``incidents``); none in custom missions.
        self._reset_incidents()
        # A running baffle clearing of the Bridge (save ``baffle_clear``).
        self.baffle_clear = None
        # The AI hunters' ESM bearing lines for a cross-fix (save ``hunter_esm``).
        self.hunter_esm = []
        # Their lead: HQ's start report or a lost submarine bearing (save
        # ``hunter_lead``).
        self.hunter_lead = None
        # The radio room's own calls to HQ (save ``hq_reports``).
        self._reset_hq_reports()
        # Watches, fatigue and morale of the frigate crew (save ``watch``).
        self._reset_crew()
        # Post-mission debrief recording (transient, never saved).
        self._reset_debrief()
        # What the enemy learnt of the player's habits (decision saved as ``habits``).
        self._reset_habits()
        # The language model's mission state (advisor mark saved, rest transient).
        if hasattr(self, "llm"):
            self._reset_llm_mission()
        # A guided lesson's coach (set by start_training, never saved).
        self.training = None
        # Whether this mission is the current campaign leg (never saved).
        self.campaign_mission = False
        self.campaign_hotspot = None
        self._campaign_leg_shown = False
        self.mission_result = None   # None | "SIEG" | "VERLOREN"
        self.result_reason = ""

        def at_dist(min_nm, max_nm):
            ang = rng.uniform(0, 360)
            dist = rng.uniform(min_nm, max_nm)
            x = config.clamp(
                self.ship.x + dist * math.cos(math.radians(ang)),
                5.0, self.world.size_nm - 5.0)
            y = config.clamp(
                self.ship.y + dist * math.sin(math.radians(ang)),
                5.0, self.world.size_nm - 5.0)
            return self.world.nearest_water(x, y)  # W3: nie in Land spawnen

        # U-Boote laut Mission + Custom-Difficulty (second_sub_prob -> Bonus-Boot)
        lv = self.difficulty
        plan = list(self.mission.sub_types)
        if (len(plan) < 3 and lv["second_sub_prob"] > 0.0
                and rng.random() < lv["second_sub_prob"]):
            plan.append(rng.choice(config.SECOND_SUB_POOL))
        self.subs = []
        for i, stype in enumerate(plan):
            min_d, max_d = ((self.mission.spec.get("short_spawn_nm",
                                                   config.SHORT_SUB_SPAWN_NM[0]) if i == 0
                             else config.SHORT_SUB_SPAWN_NM[1]) if self.short_mission
                            else (self.mission.spec or {}).get("spawn_nm", (12.0, 20.0)) if i == 0
                            else (22.0, 45.0))
            sx, sy = at_dist(min_d, max_d)
            s = Sub(sx, sy,
                    depth_m=rng.uniform(40.0, min(
                        100.0, self.runtime_catalog.subs[stype].max_depth_m * 0.5)),
                    course_deg=rng.uniform(0, 360), stype_key=stype, rng=rng,
                    quiet_mult=lv["quiet_mult"],
                    attack_mult=lv["enemy_attack_mult"],
                    attack_cooldown_s=lv["enemy_cooldown_s"],
                    solution_threshold=lv["enemy_solution_threshold"],
                    profile=self.runtime_catalog.subs[stype],
                    decoy_profile=self.runtime_catalog.decoys[
                        self.runtime_catalog.runtime_bindings["submarine_decoy"]],
                     enemy_torpedo_profile=self.runtime_catalog.torpedoes[
                         self.runtime_catalog.runtime_bindings["enemy_torpedo"]],
                    side="hostile", runtime_catalog=self.runtime_catalog,
                    asw_rng=self.rng_asw)
            self.subs.append(s)

        # Meerestiere (M4): Falschkontakte
        self.animals = []
        for _ in range(self.mission.animal_count):
            ax, ay = at_dist(15.0, 90.0)
            animal_key = rng.choice(["whale", "fish_school", "jellyfish"])
            self.animals.append(Animal(
                ax, ay, animal_key, rng=rng,
                profile=self.runtime_catalog.animals[animal_key]))

        # Zivile Schiffe (M4): AIS + Radar, jetzt auch passive Sonarkontakte
        self.civilians = []
        for _ in range(self.mission.civilian_count):
            cx, cy = at_dist(20.0, 100.0)
            merchant = CivilianShip(
                cx, cy, rng=rng,
                profile=self.runtime_catalog.pick_surface(rng, hostile=False),
                side="neutral", doctrine="surface_transit",
                runtime_catalog=self.runtime_catalog)
            traffic.assign_lane(merchant, self.seed, self.world)
            self.civilians.append(merchant)

        # A boat mission's own units: the convoy, the strait's traffic, the
        # supply ship, and the boat at its start (src/core/boat_missions.py).
        boat_missions.setup(self)

        # KAMPFSCHIFF (Kontakt-DB): feindliche Kriegsschiffe loiteren um
        # die feindliche Basis und feuern ASM, wenn die Fregatte naehert.
        self.warships = []
        self.warship_anchor = None
        base = self.world.coast.hostile_base()
        if base is not None and self.mission.warship_count > 0:
            bx, by = self.world.nearest_water(
                base["x"] + rng.uniform(-30.0, 30.0),
                base["y"] + rng.uniform(-30.0, 30.0))
            self.warship_anchor = (bx, by)
            for _ in range(self.mission.warship_count):
                angle = rng.uniform(0.0, math.tau)
                radius = rng.uniform(8.0, 18.0)
                wx, wy = self.world.nearest_water(
                    bx + math.cos(angle) * radius,
                    by + math.sin(angle) * radius)
                w = SurfaceShip(
                    wx, wy, rng=rng, hostile=True,
                    profile=self.runtime_catalog.pick_surface(rng, hostile=True),
                    side="hostile", doctrine="surface_combatant",
                    runtime_catalog=self.runtime_catalog)
                w.anchor = self.warship_anchor
                self.warships.append(w)
        # Group hunt: the consort destroyer on its formation station.
        self._setup_consort()

        # W2: Akustische Dekoys (werden bei Torpedo-Alarm abgeworfen)
        self.decoys = []
        self.incident = False
        self.station = Station.BRIDGE
        self.autocrew = AutocrewController()
        self.autocrew_overview_open = False
        self.weather_station_open = False
        # The top bar's game menu (src/ui/game_menu.py): display state only.
        self.game_menu_open = False
        # F11 event history/telemetry overlay: display only, never an input
        # owner, so every station stays operable underneath it.
        self.feed_overlay_open = False
        self.feed_overlay_scroll = 0
        self.running = True
        self.simlog_view_open = False
        self.simlog_view_scroll = 0
        self.simlog_view_map = False
        self.simlog_map_fit = simlog_map.FIT_WORLD
        self.held = set()
        self._pointer_held = None
        self._map_drag = None
        self._map_drag_moved = False
        # Waffenzentrale (M3, Munitionsbestand aus Custom-Difficulty)
        self._ownship_loadout = copy.deepcopy(ownship_loadout())
        self.player_torpedo_battery = WeaponBattery.ownship(
            int(self.difficulty["torpedo_count"]), self._ownship_loadout)
        self.torpedo_total = self.player_torpedo_battery.capacity_total
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.torpedo_depth = 60.0
        # Operator weapon settings (save v15 ``weapon_settings``): torpedo type,
        # terminal search pattern, seeker enable point and salvo size.
        self.torpedo_type = self._ownship_loadout["weapons"][0]["key"]
        self.player_torpedo_battery.preferred_weapon_key = self.torpedo_type
        self.torpedo_pattern = "snake"
        self.torpedo_enable_nm = config.TORP_HOME_RANGE_NM
        self.torpedo_salvo = 1
        self.target = None
        self.selected_contact = None  # M9: im Sonar-Panel markierter Kontakt
        self.torpedoes = []
        self.torpedo_seq = 0
        self.asrocs = []
        self.asroc_seq = 0
        # Depth charges in the water and the ship's own ASROC/depth-charge
        # stores (save ``asw.depth_charges``/``own_stores``).
        self.depth_charges = []
        self.depth_charge_seq = 0
        self.depth_charges_left = depth_charge.DEPTH_CHARGE_STOCK
        self.depth_charge_reload_s = 0.0
        self.own_asrocs_left = depth_charge.OWN_ASROC_STOCK
        # The ASW rocket launcher (save ``rbu``).
        self._reset_rbu()
        self.nixie_store = ConsumableStore.ownship(self._ownship_loadout)
        self.nixies = []
        self.nixie_seq = 0
        self.msg = ""
        self.msg_until = 0.0
        self.input_mode = None       # "course" or "speed"
        self.input_buffer = ""
        self._t = 0.0
        self.auto_quit = None  # Test-Hook: Frames bis Auto-Ende
        # M5: Schadensmodell + Gegentorpedos (Reparatur-Faktor aus Custom-Difficulty)
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=self.difficulty["repair_mult"])
        # Wounded crew of the frigate and the submarines (save ``casualties``).
        self._reset_casualties()
        self.enemy_torpedoes = []
        # Presentation-only torpedo intercept memory (see _update_torpedo_cues);
        # rebuilt from the saved torpedo state on load, never saved itself.
        self.torpedo_cues = []
        self._torpedo_cues_reported = weakref.WeakKeyDictionary()
        self.game_over = False
        # M10–M16
        self.sonar_mode = "BOW"                      # "BOW" | "TOWED"
        self.sonar_page = 0
        self.station_page = 0
        self.lookout_range_nm = 12.0                 # bridge lookout page scale (UI only)
        self.lookout_glasses = False                 # binoculars over the chart (UI only)
        self.lookout_glasses_rel = 0.0               # their line of sight off the bow
        self.lookout_optics = optics.lookout_glasses()  # tilt, zoom, stabilizer (UI only)
        self.helo_acoustic_page = 1
        self.sonar_harmonic_hz = None
        # Operator LOFAR/DEMON tools: cursor, marks, integration (UI only).
        self.sonar_tools = analysis_tools.AcousticToolState()
        # Operator TMA hypotheses per sonar target (transient UI state).
        self.tma_hypotheses = {}
        # Shared operator plot layer (chart marks, rulers, bearing lines...).
        self.plot = PlotLayer()
        self._reset_plot_ui()
        # The Bridge's autopilot route (save v28 ``route``).
        self.route = Route()
        # Display-only CRT controls are intentionally transient: they affect no
        # observation, simulation or v10 save contract.
        self.sonar_display_palette = "green"
        self.sonar_display_black = 0.0
        self.sonar_display_contrast = 1.6
        self.sonar_display_history = 1.0
        self.sonar_audio_enabled = True
        self.helo_audio_enabled = True
        self.sonar_volume = 0.5
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False
        # Local ESM cues belong to the ELOKA workstation.  The browser receives
        # the detached event separately and applies its own role/audio gate.
        self.eloka_audio_enabled = True
        self.surface_radar_on = config.RADAR_ON_DEFAULT
        self.air_radar_on = config.RADAR_ON_DEFAULT
        self.opz_range_nm = config.RADAR_RANGE_DEFAULT_NM
        self.roe = config.ROE_DEFAULT                # "STD" | "FREE"
        self.messages: list = []                     # Funkraum-Teletype
        self._reset_lookout_reports()
        self.dmg_cursor = 0
        self.dmg_team = 1
        self.helo = Helicopter(
            random.Random(seed + 555), self.runtime_catalog.torpedoes[
                self.runtime_catalog.runtime_bindings["helicopter_torpedo"]])
        self.buoys = []
        self.buoy_seq = 0
        # The maritime patrol aircraft on call (save ``mpa``).
        self._reset_mpa()
        self.helo_buoy_mode = "PASSIVE"
        self.helo_sensor_source = "DIP"
        self.helo_listen_source = "DIP"
        self.helo_listen_bearing = None
        self.helo_audio_band = "FULL"
        self.helo_audition = SonarSystem(seed=seed + 45678, acoustic_profiles=())
        self.helo_receiver = AcousticReceiver(seed=seed + 45677)
        self.helo_spectra = []
        self.helo_broadband_history = []
        self.helo_demon_history = []
        self._helo_receiver_timer = 0.0
        self.asms = []
        self.essms = []
        self._air_defense_loadout = copy.deepcopy(air_defense_loadout())
        self.asm_speed_kn = self._air_defense_loadout["asm"]["speed_kn"]
        self.vls_loadout_total = self._air_defense_loadout["vls"]["sam_loadout"]
        self.vls_cells = self._air_defense_loadout["vls"]["sam_loadout"]
        self.essm_seq = 0
        self.softkill_store = make_softkill_store(self._air_defense_loadout)
        self.chaff_cd = 0.0
        self.chaff_clouds: list = []
        self.chaff_seq = 0
        self.ciws_mount_deg = 0.0
        self.rng_asm = random.Random(seed + 31337)
        self.asm_spawned = 0
        self.asm_seq = 0
        self.air_threat_reported = False
        self.warship_asm_seq = 0
        self.asm_sel = 0
        self.air_picture = TrackPicture(
            config.RADAR_TRACK_STALE_S, maximum=MAX_AIR_PICTURE_TRACKS)
        # Unmarked mast/snorkel echoes and the boats whose echoes the OPZ
        # marked into a track: sub id -> (track id, last echo). Saved since
        # v25 (``radar_marks``): the AI hunters act on them.
        self.radar_blips = deque(maxlen=config.RADAR_BLIP_MAX)
        self.radar_blip_seq = 0
        self._radar_marked = {}
        self.ais = AISReceiver(seed)
        self.opz_selected_track_id = None
        self.opz_contact_filter = "ALL"
        # Selected row of the OPZ's Display page (display only, not saved).
        self.opz_display_sel = 0
        self.opz_affiliations = {}
        # Operator-authored display identifiers are deliberately separate from
        # opaque observation IDs.  Every station renders these labels while
        # commands continue to use the non-public observation identity.
        self.opz_track_labels = {}
        self.opz_fusion = OPZFusionPicture()
        # Simulation-time step of the last automatic OPZ fusion pass.
        self._opz_auto_fuse_step = None
        self._opz_source_bindings = {}
        self._opz_world_identity = id(self.world)
        self.esm_picture = ESMPicture()
        self.ecm_jammer = ECMJammer()
        self.eloka_selected_track_key = None
        self.eloka_status_filter = "OPERATIONAL"
        self.eloka_threat_filter = "ALL"
        self.eloka_band_filter = "ALL"
        # Intercepts of one signal kind and bearing shown as one emitter (Z).
        self.eloka_group_emitters = True
        self._eloka_group_cache = None
        self.eloka_annotations = {}
        self.radio_picture = TrackPicture(300.0)
        self.radio_sel = 0
        self.hfdf_log = []
        self.hfdf_fixes = {}
        self.ciws_ammo = self._air_defense_loadout["ciws"]["ammo"]
        self.ciws_cooldown_s = 0.0
        # Rotating search antenna in simulation time (saved): targets are
        # looked at only when the beam sweeps past them.
        self.radar_scan_phase = 0.0
        self.radar_scan_pending_deg = 0.0
        self.ciws_authorized = True  # session-only fire-release gate, OPZ "I"
        self.aa_ammo = self._air_defense_loadout["aa_gun"]["ammo"]
        self.aa_cooldown_s = 0.0
        self.flak_authorized = True  # session-only fire-release gate, Weapons "F"
        # Real ADS-B traffic: HOSTILE is a manual OPZ classification (see
        # affiliate_opz_observation) but never authorizes weapons on its own -
        # engaging a real contact needs an explicit, freshly re-affirmed
        # confirmation so an accidental IFF slip can't autofire straight into
        # a political incident.
        self.live_engage_confirm_pending = None  # icao24 awaiting confirmation
        self.live_engage_authorized = set()       # icao24s cleared to engage
        self.raiders = []
        self.raid_seq = 0
        self.raid_waves_spawned = 0
        self._raider_visible_last = False
        self.rng_raid = random.Random(seed + 40424)
        self.hq_timer = 15.0
        self._mission_warnings = set()
        self.tooltips_enabled = self.preferences.tooltips
        self.pinned_tooltip = None
        self._tooltip_anchor = None
        self._nav_warning_cd = 0.0
        self.quit_confirm = False
        self.quit_selection = 0
        self.quit_after_save = False
        self.help_open = False
        self.nations_open = False
        self.save_ui = None
        self.save_confirm = False
        self.save_info = []
        self.help_page = 0
        self.help_manual_chapter = 0
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        # W3: Luftfahrt (Airbases + Flüge) und W0: Karten-Viewport
        self.flights = FlightManager(
            self.world.coast, random.Random(seed + 2024), self.runtime_catalog,
            near=(self.ship.x, self.ship.y))
        self.map_view = Viewport(self.world.size_nm,
                                 config.MAP_ZOOM_MIN_PX_PER_NM,
                                 config.MAP_ZOOM_MAX_PX_PER_NM)
        self.opz_map_view = Viewport(self.world.size_nm, 1.0, 100.0)
        self.chart_history = ChartHistory()
        # Display only: water columns, fire and sinkings the eyes can see.
        self.sight_events = SightEvents()
        # Display only: ping wavefronts, echoes and splashes on the charts.
        self.map_fx = MapFx()
        self._reset_map_view()
        self.hq_msg(message("runtime.hq.roe", roe=self.roe))
        weather = self.world.weather_values()
        self.hq_msg(message(
            "runtime.hq.weather", sea_state=f"{weather['sea_state']:.1f}",
            wind_from=f"{weather['wind_from_deg']:.0f}",
            wind_speed=f"{weather['wind_speed_kn']:.0f}",
            rain=f"{weather['rain_intensity']:.0%}",
            visibility=f"{weather['visibility_nm']:.1f}"))
        self.feed.add(self.world.format_time(), "mission",
                      self._mission_started_notice())
        if publish_intel:
            self.hq_msg(self._initial_threat_notice())
            if self.hq_intel_mode() == "exact":
                self.hq_msg(self._threat_identification_notice())
        # Menu input cannot operate the simulation. Only this unstarted world
        # may be consumed by menu start; loads replace its world/sonar identity.
        self._prepared_menu_mission = (
            seed, self.scenario_key, self.world_mode,
            self._difficulty_base, self.hq_intel_mode(), self.level,
            self.start_weather, self.start_time, self.start_length,
            id(self.world), id(self.sonar)) if self.in_menu else None

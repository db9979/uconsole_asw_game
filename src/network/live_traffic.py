"""Orchestriert AIS-Stream- und OpenSky-ADS-B-Verkehr in der Spielwelt.

``LiveTrafficManager`` ist die einzige Andockstelle, die ``Game`` kennen
muss: ``configure()`` einmal pro neuer Welt/Mission, ``pump()`` einmal pro
Frame (analog zu ``Commander.pump``), ``stop()`` beim Beenden. Alles
Netzwerk-/Threading-Detail bleibt in ``ais_client``/``adsb_client``
gekapselt; hier werden nur Queues geleert und Spiel-Entities erzeugt/
aktualisiert - ausschliesslich im Hauptthread.
"""

from __future__ import annotations

import math
import queue
import random
import time

from src.enemies.surface import SurfaceShip
from src.air.live_aircraft import LiveAircraft
from src.network.ais_client import AisStreamClient
from src.network.adsb_client import OpenSkyClient
from src.world.projection import lonlat_to_nm, nm_to_lonlat

# Minimalintervall zwischen zwei angewandten AIS-Positions-/Kursupdates pro
# Schiff - haelt die taktische Darstellung frei von Mikroruckeln, siehe
# Auftragsvorgabe (2-5 Minuten, hier gejittert pro MMSI).
_AIS_APPLY_MIN_S = 120.0
_AIS_APPLY_MAX_S = 300.0

# Performance: ein AIS-Stream/OpenSky-Feed fuer die ganze 500-NM-Welt kann in
# dicht befahrenen Realgebieten (Haefen, grosse Flughaefen) hunderte Kontakte
# liefern. Jeder zusaetzliche simulierte Kontakt kostet Radar-/Sonar-/Physik-
# Rechenzeit pro Frame, unabhaengig davon, ob er fuer die Taktik relevant ist.
# Deshalb: nur Kontakte in Sensor-Reichweite der Fregatte werden ueberhaupt
# gespawnt, spaeter irrelevant gewordene (weit weg getrieben/keine Updates
# mehr) werden wieder entfernt - plus eine harte Obergrenze als Notbremse.
_SHIP_RELEVANCE_NM = 150.0        # deckt auch die maximale ESM-Reichweite ab
_SHIP_RELEASE_NM = 190.0          # Hysterese: erst spaeter wieder entfernen
_SHIP_STALE_S = 900.0             # 15 min ohne jeden AIS-Report -> vergessen
_MAX_LIVE_SHIPS = 60
_MAX_AIS_METADATA = 2048
_AIS_MIN_MOVING_SOG_KN = 0.1      # AIS-Aufloesung: 0.0 kn bedeutet Stillstand

_AIRCRAFT_RELEVANCE_NM = 150.0
_AIRCRAFT_RELEASE_NM = 200.0
_AIRCRAFT_STALE_S = 450.0         # mehrere verpasste ~180s-Polls -> vergessen
_MAX_LIVE_AIRCRAFT = 40
_ADSB_QUERY_MARGIN_NM = 25.0
_ADSB_REBIND_NM = 25.0

_AIS_METADATA_FIELDS = (
    "name", "callsign", "imo", "ship_type", "destination", "draught_m",
    "length_m", "width_m", "nav_status", "heading", "position_accuracy",
)


def _category_for_ais_type(ship_type: int | None) -> str:
    """AIS 'Type of ship and cargo' -> Katalog-Kategorie."""
    if ship_type is None:
        return "SONSTIGES"
    if 60 <= ship_type <= 69:
        return "PASSAGIER"
    if 70 <= ship_type <= 79:
        return "FRACHT"
    if 80 <= ship_type <= 89:
        return "TANKER"
    return "SONSTIGES"


def _valid_cog(value) -> float | None:
    """AIS COG in Grad; 360.0 (und darueber) bedeutet 'nicht verfuegbar'."""
    if value is None:
        return None
    value = float(value)
    return value if 0.0 <= value < 360.0 else None


def _valid_sog(value) -> float | None:
    """AIS SOG in kn; 102.3 (und darueber) bedeutet 'nicht verfuegbar'."""
    if value is None:
        return None
    value = float(value)
    return value if 0.0 <= value < 102.3 else None


class LiveTrafficManager:
    """Haelt Live-AIS-Schiffe und Live-ADS-B-Flugzeuge synchron zum Spiel."""

    def __init__(self) -> None:
        self.ais_client: AisStreamClient | None = None
        self.adsb_client: OpenSkyClient | None = None
        self.aircraft: dict[str, LiveAircraft] = {}
        self.online = False
        self._ships: dict[int, SurfaceShip] = {}
        self._ship_types: dict[int, int] = {}
        self._ship_metadata: dict[int, dict] = {}
        self._next_apply_at: dict[int, float] = {}
        self._ship_last_seen: dict[int, float] = {}
        self._destroyed_mmsi: set[int] = set()
        self._destroyed_icao24: set[str] = set()
        # Ueberlebt Prune+Respawn (siehe `_prune_ships`/`_prune_aircraft`):
        # ohne diese Zuordnung wuerde ein Kontakt, der wegen eines
        # Feed-Ausfalls kurz verworfen wird und danach wieder berichtet,
        # eine neue Track-ID bekommen, waehrend der alte Track im
        # Sensorbild noch kurz nachlebt - sichtbar als zwei ueberlagerte
        # Symbole fuer denselben realen Kontakt.
        self._ship_civ_id: dict[int, int] = {}
        self._aircraft_seq: dict[str, int] = {}
        self._center: tuple[float, float] | None = None
        self._size_nm: float = 0.0
        self._adsb_anchor: tuple[float, float] | None = None

    # --- Lebenszyklus ---------------------------------------------------

    def configure(self, game, world, preferences) -> None:
        """(Re-)konfiguriert fuer eine (neue) Welt/Mission und Einstellungen."""
        self.stop()
        self._ships.clear()
        self._ship_types.clear()
        self._ship_metadata.clear()
        self._next_apply_at.clear()
        self._ship_last_seen.clear()
        self._destroyed_mmsi.clear()
        self._destroyed_icao24.clear()
        self._ship_civ_id.clear()
        self._aircraft_seq.clear()
        self.aircraft.clear()
        self._center = None
        self._adsb_anchor = None
        metadata = getattr(world.coast, "metadata", None)
        center = metadata.get("center") if metadata else None
        if center is None:
            return  # Keine reale Geographie fuer dieses Szenario hinterlegt.
        self._center = (float(center["longitude"]), float(center["latitude"]))
        self._size_nm = float(world.size_nm)
        bbox_latlon = self._bounding_box_latlon()
        if preferences.live_ais_enabled and preferences.aisstream_api_key.strip():
            self.ais_client = AisStreamClient(
                preferences.aisstream_api_key.strip(), bbox_latlon)
            self.ais_client.start()
        if preferences.live_adsb_enabled:
            self._adsb_anchor = (float(game.ship.x), float(game.ship.y))
            self.adsb_client = OpenSkyClient(
                preferences.opensky_credentials.strip(),
                self._adsb_bounding_box(*self._adsb_anchor))
            self.adsb_client.start()

    def stop(self) -> None:
        if self.ais_client is not None:
            self.ais_client.stop()
            self.ais_client = None
        if self.adsb_client is not None:
            self.adsb_client.stop()
            self.adsb_client = None

    def _bounding_box_latlon(self):
        center_lon, center_lat = self._center
        lon_a, lat_a = nm_to_lonlat(
            0.0, self._size_nm, center_lon, center_lat, self._size_nm)
        lon_b, lat_b = nm_to_lonlat(
            self._size_nm, 0.0, center_lon, center_lat, self._size_nm)
        lat_min, lat_max = sorted((lat_a, lat_b))
        lon_min, lon_max = sorted((lon_a, lon_b))
        return ((lat_min, lon_min), (lat_max, lon_max))

    def _adsb_bounding_box(self, x_nm: float, y_nm: float):
        """Query the ship's sensor neighborhood, clipped to the real sector."""
        radius = _AIRCRAFT_RELEVANCE_NM + _ADSB_QUERY_MARGIN_NM
        x_min = max(0.0, x_nm - radius)
        x_max = min(self._size_nm, x_nm + radius)
        y_min = max(0.0, y_nm - radius)
        y_max = min(self._size_nm, y_nm + radius)
        center_lon, center_lat = self._center
        lon_min, lat_min = nm_to_lonlat(
            x_min, y_max, center_lon, center_lat, self._size_nm)
        lon_max, lat_max = nm_to_lonlat(
            x_max, y_min, center_lon, center_lat, self._size_nm)
        if lon_min > lon_max:
            # A single OpenSky box cannot wrap across the antimeridian.
            # Cover both sides until the ship moves back into a normal box.
            lon_min, lon_max = -180.0, 180.0
        return ((lat_min, lon_min), (lat_max, lon_max))

    def _refresh_adsb_bounding_box(self, game) -> None:
        client = self.adsb_client
        if client is None:
            return
        position = (float(game.ship.x), float(game.ship.y))
        anchor = self._adsb_anchor
        if anchor is None or math.hypot(position[0] - anchor[0],
                                         position[1] - anchor[1]) >= _ADSB_REBIND_NM:
            client.set_bounding_box(self._adsb_bounding_box(*position))
            self._adsb_anchor = position

    # --- Zerstoerung ------------------------------------------------------

    def mark_ship_destroyed(self, mmsi: int | None) -> None:
        if mmsi is None:
            return
        self._destroyed_mmsi.add(mmsi)
        self._ships.pop(mmsi, None)
        self._ship_types.pop(mmsi, None)
        self._ship_metadata.pop(mmsi, None)
        self._next_apply_at.pop(mmsi, None)
        self._ship_last_seen.pop(mmsi, None)
        self._ship_civ_id.pop(mmsi, None)

    def mark_aircraft_destroyed(self, icao24: str | None) -> None:
        if icao24 is None:
            return
        self._destroyed_icao24.add(icao24)
        self.aircraft.pop(icao24, None)
        self._aircraft_seq.pop(icao24, None)

    # --- Pro-Frame-Pumping --------------------------------------------

    def pump(self, game) -> None:
        if self._center is None:
            return
        self._refresh_adsb_bounding_box(game)
        self._drain_ais(game)
        self._drain_adsb(game)
        now = time.time()
        for aircraft in self.aircraft.values():
            aircraft.advance(now)
        self._prune_ships(game, now)
        self._prune_aircraft(game, now)

    def _prune_ships(self, game, now: float) -> None:
        """Entfernt Live-Schiffe, die weit weg getrieben sind oder lange
        keinen AIS-Report mehr geliefert haben - haelt die Kontaktzahl (und
        damit Radar-/Sonar-/Physik-Kosten pro Frame) unabhaengig von der
        Verkehrsdichte im realen Gebiet begrenzt. Versenkte Wracks bleiben
        unabhaengig davon erhalten (Spielkonvention)."""
        stale = []
        for mmsi, ship in self._ships.items():
            if ship.sunk:
                continue
            last_seen = self._ship_last_seen.get(mmsi, now)
            far = math.hypot(ship.x - game.ship.x,
                             ship.y - game.ship.y) > _SHIP_RELEASE_NM
            if now - last_seen > _SHIP_STALE_S or far:
                stale.append(mmsi)
        if not stale:
            return
        drop = set(stale)
        game.civilians = [c for c in game.civilians
                          if getattr(c, "live_mmsi", None) not in drop]
        for mmsi in stale:
            self._ships.pop(mmsi, None)
            self._ship_types.pop(mmsi, None)
            self._ship_metadata.pop(mmsi, None)
            self._next_apply_at.pop(mmsi, None)
            self._ship_last_seen.pop(mmsi, None)

    def _prune_aircraft(self, game, now: float) -> None:
        """Analog zu `_prune_ships`, aber Flugzeuge werden - wie despawnte
        Raider/Fluege - komplett entfernt statt als Wrack zu verbleiben."""
        stale = [icao24 for icao24, aircraft in self.aircraft.items()
                if aircraft.despawned
                or now - aircraft.last_fix_at > _AIRCRAFT_STALE_S
                or math.hypot(aircraft.x - game.ship.x,
                             aircraft.y - game.ship.y) > _AIRCRAFT_RELEASE_NM]
        for icao24 in stale:
            self.aircraft.pop(icao24, None)

    def _drain_ais(self, game) -> None:
        client = self.ais_client
        if client is None:
            return
        while True:
            try:
                report = client.reports.get_nowait()
            except queue.Empty:
                break
            mmsi = report.get("mmsi")
            if mmsi is None or mmsi in self._destroyed_mmsi:
                continue
            ship_type = report.get("ship_type")
            if ship_type is not None:
                self._ship_types[mmsi] = ship_type
            metadata = self._merge_ais_metadata(mmsi, report)
            ship = self._ships.get(mmsi)
            if ship is not None:
                self._apply_ais_metadata(ship, metadata)
                self._ship_last_seen[mmsi] = time.time()
            if report.get("lat") is None or report.get("lon") is None:
                continue
            self._apply_ais_report(game, mmsi, report)

    def _merge_ais_metadata(self, mmsi: int, report: dict) -> dict:
        """Merge allowlisted fields while keeping the long-running feed bounded."""
        if mmsi not in self._ship_metadata:
            if len(self._ship_metadata) >= _MAX_AIS_METADATA:
                oldest = next(iter(self._ship_metadata))
                victim = next((key for key in self._ship_metadata
                               if key not in self._ships), oldest)
                self._ship_metadata.pop(victim, None)
                self._ship_types.pop(victim, None)
        metadata = self._ship_metadata.setdefault(mmsi, {})
        metadata.update({key: report[key] for key in _AIS_METADATA_FIELDS
                         if report.get(key) is not None})
        return metadata

    @staticmethod
    def _apply_ais_metadata(ship: SurfaceShip, metadata: dict) -> None:
        """Attach detached, allowlisted feed metadata to a live entity."""
        name = metadata.get("name")
        callsign = metadata.get("callsign")
        if name:
            ship.name = name
        if callsign:
            ship.callsign = callsign
        ship.live_ais_details.update({
            key: metadata[key] for key in _AIS_METADATA_FIELDS
            if key not in {"name", "callsign"} and metadata.get(key) is not None
        })

    def _remove_simulated_ais_ship(self, game, mmsi: int,
                                   ship: SurfaceShip | None) -> None:
        """Drop only the entity; retain identity/static data for a later fix."""
        if ship is not None:
            game.civilians = [civilian for civilian in game.civilians
                              if civilian is not ship]
        self._ships.pop(mmsi, None)
        self._next_apply_at.pop(mmsi, None)
        self._ship_last_seen.pop(mmsi, None)

    def _apply_ais_report(self, game, mmsi: int, report: dict) -> None:
        now = time.time()
        ship = self._ships.get(mmsi)
        metadata = self._merge_ais_metadata(mmsi, report)
        if report.get("ship_type") is not None:
            self._ship_types[mmsi] = report["ship_type"]
        x, y = lonlat_to_nm(report["lon"], report["lat"], *self._center,
                            self._size_nm)
        sog = _valid_sog(report.get("sog"))
        if sog is not None and sog < _AIS_MIN_MOVING_SOG_KN:
            self._remove_simulated_ais_ship(game, mmsi, ship)
            return
        on_land = getattr(getattr(game, "world", None), "on_land", None)
        if callable(on_land) and on_land(x, y):
            # Coarse public AIS positions around ports can fall inside the
            # packaged coastline polygon. Such contacts must not become
            # simulated ships or leak into any sensor picture. If an existing
            # live ship moves onto mapped land, remove it until a later valid
            # water position arrives; keep its stable ID and static metadata.
            if ship is not None:
                self._remove_simulated_ais_ship(game, mmsi, ship)
            return
        if ship is None:
            # Nur Kontakte, die tatsaechlich in Sensor-Reichweite (inkl. ESM-
            # Reichweite als groesster Sensor-Radius) liegen koennen, werden
            # ueberhaupt simuliert - siehe Modulkommentar zu den Konstanten.
            if (len(self._ships) >= _MAX_LIVE_SHIPS
                    or math.hypot(x - game.ship.x, y - game.ship.y)
                    > _SHIP_RELEVANCE_NM):
                return
            category = _category_for_ais_type(self._ship_types.get(mmsi))
            rng = random.Random(mmsi)
            profile = game.runtime_catalog.pick_civilian_by_category(rng, category)
            ship = SurfaceShip(
                x, y, rng, side="neutral", doctrine="surface_transit",
                profile=profile, runtime_catalog=game.runtime_catalog)
            civ_id = self._ship_civ_id.get(mmsi)
            if civ_id is None:
                self._ship_civ_id[mmsi] = ship.id
            else:
                ship.id = civ_id
            ship.live_mmsi = mmsi
            self._apply_ais_metadata(ship, metadata)
            cog = _valid_cog(report.get("cog"))
            if cog is not None:
                ship.course = ship.target_course = float(cog)
            if sog is not None:
                ship.speed = ship.target_speed = float(sog)
            self._ships[mmsi] = ship
            self._next_apply_at[mmsi] = now + random.uniform(
                _AIS_APPLY_MIN_S, _AIS_APPLY_MAX_S)
            self._ship_last_seen[mmsi] = now
            game.civilians.append(ship)
            return
        self._apply_ais_metadata(ship, metadata)
        self._ship_last_seen[mmsi] = now
        if ship.sunk or now < self._next_apply_at.get(mmsi, 0.0):
            return
        self._next_apply_at[mmsi] = now + random.uniform(
            _AIS_APPLY_MIN_S, _AIS_APPLY_MAX_S)
        ship.x, ship.y = x, y
        cog = _valid_cog(report.get("cog"))
        if cog is not None:
            ship.target_course = float(cog)
        if sog is not None:
            ship.target_speed = float(sog)

    def _drain_adsb(self, game) -> None:
        client = self.adsb_client
        if client is None:
            return
        snapshot_t = None
        states = None
        while True:
            try:
                snapshot_t, states = client.snapshots.get_nowait()
            except queue.Empty:
                break
        if states is None:
            return
        for state in states:
            # OpenSky states[i] Layout: [icao24, callsign, origin_country,
            # time_position, last_contact, lon, lat, baro_altitude,
            # on_ground, velocity, true_track, vertical_rate, ...]
            if not state or len(state) < 11:
                continue
            icao24 = state[0]
            if not icao24 or icao24 in self._destroyed_icao24:
                continue
            lon, lat, altitude_m = state[5], state[6], state[7]
            velocity_ms, heading, on_ground = state[9], state[10], state[8]
            if lon is None or lat is None or on_ground:
                continue
            x, y = lonlat_to_nm(lon, lat, *self._center, self._size_nm)
            altitude_m = float(altitude_m) if altitude_m is not None else 0.0
            heading = float(heading) if heading is not None else 0.0
            speed_kn = float(velocity_ms) * 1.9438445 if velocity_ms is not None else 0.0
            existing = self.aircraft.get(icao24)
            if existing is None:
                if (len(self.aircraft) >= _MAX_LIVE_AIRCRAFT
                        or math.hypot(x - game.ship.x, y - game.ship.y)
                        > _AIRCRAFT_RELEVANCE_NM):
                    continue
                # Geteilter Zaehler mit FlightManager: reale und simulierte
                # Fluege sind ueber die Track-ID (A-<seq>) nicht
                # unterscheidbar, siehe FlightManager.next_seq(). Ein
                # bereits vergebener Seq fuer dieselbe ICAO24 wird
                # wiederverwendet (siehe `_aircraft_seq`-Kommentar oben).
                seq = self._aircraft_seq.get(icao24)
                if seq is None:
                    seq = game.flights.next_seq()
                    self._aircraft_seq[icao24] = seq
                self.aircraft[icao24] = LiveAircraft(
                    icao24, state[1], seq, x, y, altitude_m,
                    heading, speed_kn, snapshot_t)
            else:
                existing.push_fix(x, y, altitude_m, heading, speed_kn, snapshot_t)

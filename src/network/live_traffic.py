"""Orchestriert AIS-Stream- und OpenSky-ADS-B-Verkehr in der Spielwelt.

``LiveTrafficManager`` ist die einzige Andockstelle, die ``Game`` kennen
muss: ``configure()`` einmal pro neuer Welt/Mission, ``pump()`` einmal pro
Frame (analog zu ``Commander.pump``), ``stop()`` beim Beenden. Alles
Netzwerk-/Threading-Detail bleibt in ``ais_client``/``adsb_client``
gekapselt; hier werden nur Queues geleert und Spiel-Entities erzeugt/
aktualisiert - ausschliesslich im Hauptthread.
"""

from __future__ import annotations

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


class LiveTrafficManager:
    """Haelt Live-AIS-Schiffe und Live-ADS-B-Flugzeuge synchron zum Spiel."""

    def __init__(self) -> None:
        self.ais_client: AisStreamClient | None = None
        self.adsb_client: OpenSkyClient | None = None
        self.aircraft: dict[str, LiveAircraft] = {}
        self.online = False
        self._ships: dict[int, SurfaceShip] = {}
        self._ship_types: dict[int, int] = {}
        self._next_apply_at: dict[int, float] = {}
        self._destroyed_mmsi: set[int] = set()
        self._destroyed_icao24: set[str] = set()
        self._center: tuple[float, float] | None = None
        self._size_nm: float = 0.0
        self._aircraft_seq = 0

    # --- Lebenszyklus ---------------------------------------------------

    def configure(self, game, world, preferences) -> None:
        """(Re-)konfiguriert fuer eine (neue) Welt/Mission und Einstellungen."""
        self.stop()
        self._ships.clear()
        self._ship_types.clear()
        self._next_apply_at.clear()
        self._destroyed_mmsi.clear()
        self._destroyed_icao24.clear()
        self.aircraft.clear()
        self._center = None
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
            self.adsb_client = OpenSkyClient(
                preferences.opensky_credentials.strip(), bbox_latlon)
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

    # --- Zerstoerung ------------------------------------------------------

    def mark_ship_destroyed(self, mmsi: int | None) -> None:
        if mmsi is None:
            return
        self._destroyed_mmsi.add(mmsi)
        self._ships.pop(mmsi, None)

    def mark_aircraft_destroyed(self, icao24: str | None) -> None:
        if icao24 is None:
            return
        self._destroyed_icao24.add(icao24)
        self.aircraft.pop(icao24, None)

    # --- Pro-Frame-Pumping --------------------------------------------

    def pump(self, game) -> None:
        if self._center is None:
            return
        self._drain_ais(game)
        self._drain_adsb()
        now = time.time()
        for aircraft in self.aircraft.values():
            aircraft.advance(now)
        if any(a.despawned for a in self.aircraft.values()):
            self.aircraft = {k: v for k, v in self.aircraft.items()
                             if not v.despawned}

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
            if report.get("lat") is None or report.get("lon") is None:
                continue
            self._apply_ais_report(game, mmsi, report)

    def _apply_ais_report(self, game, mmsi: int, report: dict) -> None:
        now = time.time()
        ship = self._ships.get(mmsi)
        x, y = lonlat_to_nm(report["lon"], report["lat"], *self._center,
                            self._size_nm)
        if ship is None:
            category = _category_for_ais_type(self._ship_types.get(mmsi))
            rng = random.Random(mmsi)
            profile = game.runtime_catalog.pick_civilian_by_category(rng, category)
            ship = SurfaceShip(
                x, y, rng, side="neutral", doctrine="surface_transit",
                profile=profile, runtime_catalog=game.runtime_catalog)
            ship.live_mmsi = mmsi
            if report.get("name"):
                ship.name = report["name"]
                ship.callsign = report["name"]
            cog, sog = report.get("cog"), report.get("sog")
            if cog is not None:
                ship.course = ship.target_course = float(cog)
            if sog is not None:
                ship.speed = ship.target_speed = float(sog)
            self._ships[mmsi] = ship
            self._next_apply_at[mmsi] = now + random.uniform(
                _AIS_APPLY_MIN_S, _AIS_APPLY_MAX_S)
            game.civilians.append(ship)
            return
        if ship.sunk or now < self._next_apply_at.get(mmsi, 0.0):
            return
        self._next_apply_at[mmsi] = now + random.uniform(
            _AIS_APPLY_MIN_S, _AIS_APPLY_MAX_S)
        ship.x, ship.y = x, y
        cog, sog = report.get("cog"), report.get("sog")
        if cog is not None:
            ship.target_course = float(cog)
        if sog is not None:
            ship.target_speed = float(sog)

    def _drain_adsb(self) -> None:
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
                self._aircraft_seq += 1
                self.aircraft[icao24] = LiveAircraft(
                    icao24, state[1], self._aircraft_seq, x, y, altitude_m,
                    heading, speed_kn, snapshot_t)
            else:
                existing.push_fix(x, y, altitude_m, heading, speed_kn, snapshot_t)

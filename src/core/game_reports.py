"""The frigate's own radio calls to HQ in the game (radio room, page 3).

``hq_reports.py`` holds the state.  A call needs a working radio room and
goes out for ``RADIO_TX_S``; while it is on the air every hostile submarine
with its antenna up (the crewed boat's raised mast, an AI boat at periscope
depth) can take an HF/DF bearing on the frigate.
"""

from __future__ import annotations

import math

from src.core import boat_radio, config, detrand
from src.core.hq_reports import HqReports
from src.core.i18n import message
from src.sensors import hfdf as hf_physics
from src.sensors.platform import MAST_DEPTH_M

# The frigate calls a shore station over a long path, like the boats do.
FRIGATE_HF_SEED = 90_210
HFDF_FIX_MAX_AGE_S = 900.0


class ReportsMixin:
    """Contact reports and support requests over HF."""

    def _reset_hq_reports(self) -> None:
        self.hq_reports = HqReports()

    def report_fix(self):
        """The position a contact report would give: the freshest located
        sonar contact, else the freshest HF/DF cross-fix, else None."""
        located = [contact for contact in self.sonar.contacts.values()
                   if self._contact_range_fresh(contact) and contact.observed_x is not None]
        if located:
            contact = min(located, key=lambda row: (self.sim_t - row.last_seen, row.id))
            return float(contact.observed_x), float(contact.observed_y)
        fixes = [(self.sim_t - fix["t"], key, fix) for key, fix in sorted(self.hfdf_fixes.items())
                 if 0.0 <= self.sim_t - fix["t"] <= HFDF_FIX_MAX_AGE_S]
        if fixes:
            fix = min(fixes)[2]
            return float(fix["x"]), float(fix["y"])
        return None

    def _report_check(self):
        if self.game_over or not self.running:
            return "not_ready"
        if self.damage.station_down("radio"):
            return "radio_down"
        if self.hq_reports.transmitting:
            return "report_transmitting"
        if self.sim_t < self.hq_reports.next_t:
            return "report_cooldown"
        return None

    def can_send_report(self, kind: str) -> bool:
        return (self._report_check() is None
                and (kind != "contact" or self.report_fix() is not None))

    def send_contact_report(self):
        """Radio the freshest fix to HQ; True or a refusal code."""
        refusal = self._report_check()
        if refusal:
            return refusal
        fix = self.report_fix()
        if fix is None:
            return "report_no_fix"
        # Scored at the mission's end only: HQ never tells the radio room.
        accurate = any(sub.side == "hostile" and not sub.sunk
                       and math.hypot(sub.x - fix[0], sub.y - fix[1])
                       <= config.CONTACT_REPORT_CONFIRM_NM for sub in self.subs)
        self.hq_reports.start("contact", self.sim_t, config.RADIO_TX_S,
                              config.RADIO_REPORT_INTERVAL_S, x=fix[0], y=fix[1],
                              accurate=accurate)
        self._report_on_air("contact")
        return True

    def request_support(self):
        """Ask HQ for support (the on-call patrol aircraft); True or a refusal."""
        refusal = self._report_check()
        if refusal:
            return refusal
        self.hq_reports.start("support", self.sim_t, config.RADIO_TX_S,
                              config.RADIO_REPORT_INTERVAL_S)
        self._report_on_air("support")
        return True

    def _report_on_air(self, kind: str) -> None:
        text = message("radio.report.sending." + kind,
                       seconds=f"{config.RADIO_TX_S:.0f}")
        self.hq_msg(text)
        self.flash(text, 3.0)
        self._report_intercepts()

    def _report_intercepts(self) -> None:
        """Hostile boats with an antenna up take an HF/DF bearing on the call."""
        night = self.world.is_night()
        window = math.floor(self.sim_t / 300.0)
        frequency = hf_physics.transmit_frequency_mhz(FRIGATE_HF_SEED, window, night)
        boat = getattr(self, "_opfor", None)
        for sub in sorted(self.subs, key=lambda item: item.id):
            if sub.sunk or sub.side != "hostile":
                continue
            crewed = boat is not None and boat.sub is sub
            if crewed:
                if not boat_radio.antenna_up(boat):
                    continue
            elif sub.depth > MAST_DEPTH_M + 1.0:
                continue
            dist = math.hypot(self.ship.x - sub.x, self.ship.y - sub.y)
            mode = hf_physics.propagation_mode(dist, frequency, night, config.HFDF_RANGE_NM)
            if mode is None or (mode == "GROUND" and self.world.land_blocks_line(
                    sub.x, sub.y, self.ship.x, self.ship.y)):
                continue
            error = config.HFDF_BEARING_ERR_DEG * (
                hf_physics.SKY_WAVE_BEARING_FACTOR if mode == "SKY" else 1.0)
            truth = math.degrees(math.atan2(self.ship.x - sub.x, -(self.ship.y - sub.y)))
            noise = detrand.normal(self.seed, "frigate-hf", sub.id,
                                   int(self.sim_t * 10.0))
            bearing = (truth + config.clamp(noise, -1.7, 1.7) * error / 1.7) % 360.0
            if crewed:
                boat.orders.event("hf_frigate", bearing=f"{bearing:03.0f}",
                                  mode=message("radio.propagation." + mode.lower()))
                rad = math.radians(bearing)
                self.plot_add("ruler", sub.x, sub.y, "HF",
                              layer=boat.plot, x2=sub.x + 30.0 * math.sin(rad),
                              y2=sub.y - 30.0 * math.cos(rad))
            elif sub.memory.get("contact") is None:
                # An AI boat learns where the call came from.
                sub.memory["contact_bearing"] = bearing

    def _update_hq_reports(self) -> None:
        reports = self.hq_reports
        if not reports.transmitting or self.sim_t < reports.tx_until:
            return
        if self.damage.station_down("radio"):
            reports.finish()
            self.hq_msg(message("radio.report.cut"))
            return
        row = reports.finish()
        if row is None:
            return
        if row["kind"] == "contact":
            self.hq_msg(message("radio.report.contact_ack",
                                x=f"{row['x']:.1f}", y=f"{row['y']:.1f}"))
            mpa = self.mpa
            if mpa.state in ("TRANSIT", "STATION"):
                mpa.set_waypoint(row["x"], row["y"])
                mpa.pattern_queue = []
                mpa.pattern = "single"
                self.hq_msg(message("radio.report.mpa_vectored"))
        elif self.mpa.launch(self.ship.x, self.ship.y, self.sim_t):
            eta = math.hypot(self.ship.x - self.mpa.x, self.ship.y - self.mpa.y) / (
                config.kn_to_nm_per_s(config.MPA_TRANSIT_KN) * 60.0)
            self.hq_msg(message("radio.report.support_mpa", minutes=f"{eta:.0f}"))
        else:
            self.hq_msg(message("radio.report.support_none"))

    def _score_hq_reports(self) -> int:
        """End of mission: points for the reports that were right."""
        count = min(config.CONTACT_REPORT_SCORED, self.hq_reports.accurate_reports())
        return count * config.SCORE_CONTACT_REPORT

    def report_view(self) -> dict:
        reports = self.hq_reports
        return dict(transmitting=reports.transmitting,
                    tx_left_s=max(0.0, reports.tx_until - self.sim_t)
                    if reports.transmitting else None,
                    ready_in_s=max(0.0, reports.next_t - self.sim_t),
                    has_fix=self.report_fix() is not None,
                    sent=len(reports.log))

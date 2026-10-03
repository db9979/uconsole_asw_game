"""The Remote Crew mission log: the same entries as the uConsole's F11 log.

The frigate's stations read the frigate's event feed (``game.feed``), the
crewed submarine's stations the boat log (``boat.feed``), each with its own
time stamp and category tag. Every new entry gets the bridge's next event
number once; the texts are localized when published (and again only after
the host language changes). Display only: nothing here is saved or reaches
the simulation.
"""

from collections import deque

from src.core import config, opfor
from src.core.i18n import localize

FRIGATE_LOG_MAX = config.FEED_MAX_ENTRIES
BOAT_LOG_MAX = opfor.OPFOR_FEED_MAX
# Tags of the browser-only alerts, in the style of the log's category tags.
ALERT_TAGS = {"damage": "SCH", "threat": "OPZ", "mission": "MIS",
              "boat_mission": "MIS", "proposal": "CREW"}


def category_tag(category: str) -> str:
    return config.FEED_CATEGORIES.get(category, (None, "?"))[1]


class MissionLog:
    def __init__(self):
        self.frigate = deque(maxlen=FRIGATE_LOG_MAX)
        self.boat = deque(maxlen=BOAT_LOG_MAX)
        self._frigate_mark = None   # (feed object id, entries added so far)
        self._boat_mark = None      # (boat object id, last boat log number)

    def clear(self) -> None:
        self.frigate.clear()
        self.boat.clear()
        self._frigate_mark = self._boat_mark = None

    @staticmethod
    def _row(seq, category, stamp, text) -> dict:
        category = str(category or "log")[:32]
        return dict(seq=seq, kind=category, stamp=str(stamp or "--:--")[:32],
                    tag=category_tag(category)[:8], text=text, _language=None,
                    _message="")

    def sync(self, game, next_seq) -> bool:
        """Take the entries added since the last call; ``next_seq()`` numbers
        each one. True when the log changed."""
        changed = False
        feed = game.feed
        if self._frigate_mark is None or self._frigate_mark[0] != id(feed):
            self.frigate.clear()
            fresh = list(feed.entries)
        else:
            count = feed.added - self._frigate_mark[1]
            fresh = feed.entries[-count:] if count > 0 else []
        self._frigate_mark = (id(feed), feed.added)
        for entry in fresh:
            self.frigate.append(self._row(next_seq(), entry.category, entry.stamp,
                                          entry.text))
            changed = True
        boat = game.opfor
        if boat is not None:
            if self._boat_mark is None or self._boat_mark[0] != id(boat):
                self.boat.clear()
                last = 0
            else:
                last = self._boat_mark[1]
            for row in boat.feed:
                if row["seq"] > last:
                    self.boat.append(self._row(next_seq(), row["category"],
                                               row.get("stamp"), row["text"]))
                    last = row["seq"]
                    changed = True
            self._boat_mark = (id(boat), last)
        return changed

    def rows(self, game, side: str) -> list:
        """The side's published rows (oldest first), localized for the host."""
        language = game.preferences.language
        published = []
        for row in self.frigate if side == "frigate" else self.boat:
            if row["_language"] != language:
                text = str(localize(row["text"], game.tr)).strip()
                row["_message"] = (text or "-")[:512]
                row["_language"] = language
            published.append(dict(seq=row["seq"], kind=row["kind"], severity="info",
                                  message=row["_message"], stamp=row["stamp"],
                                  tag=row["tag"]))
        return published

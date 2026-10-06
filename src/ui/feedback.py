"""W0: stationsübergreifender Ereignis-Feed für operative Meldungen.

Ersetzt/erweitert das alte Teletype (nur Funk): Navigation, Funk, Sonar, Waffen,
OPZ, Schaden, Mission und Weltzustand werden kategorisiert und farbcodiert in
der Bottom-Leiste gehalten. Max. FEED_MAX_ENTRIES Einträge.
"""

from src.core import config


class FeedEntry:
    __slots__ = ("stamp", "category", "text")

    def __init__(self, stamp: str, category: str, text: str):
        self.stamp = stamp
        self.category = category
        self.text = text

    def color(self) -> tuple:
        name = config.FEED_CATEGORIES.get(self.category, ("COLOR_TEXT", "?"))[0]
        # Resolved now, not at import: the colour scheme may have changed.
        return getattr(config, name)

    def tag(self) -> str:
        return config.FEED_CATEGORIES.get(self.category,
                                          (None, "?"))[1]


class EventFeed:
    def __init__(self, cap: int = config.FEED_MAX_ENTRIES, sink=None):
        self.cap = cap
        self.entries: list[FeedEntry] = []
        # Entries ever added (never reset), so a reader such as the Remote
        # Crew log can tell new entries from old ones after the cap trims.
        self.added = 0
        self._sink = sink

    def add(self, stamp: str, category: str, text: str) -> None:
        self.entries.append(FeedEntry(stamp, category, text))
        self.added += 1
        if len(self.entries) > self.cap:
            self.entries.pop(0)
        if self._sink is not None:
            self._sink(stamp, category, text)

    def recent(self, n: int) -> list[FeedEntry]:
        return self.entries[-n:]

    def clear(self) -> None:
        self.entries = []

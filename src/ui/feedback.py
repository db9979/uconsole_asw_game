"""W0: Ereignis-Feed (Bottom-Panel): Sonar-, Funk-, Schaden-, Missionsmeldungen.

Ersetzt/erweitert das alte Teletype (nur Funk): kategorisiert, farbcodiert,
lauffähig in der Bottom-Leiste. Max. FEED_MAX_ENTRIES Einträge.
"""

from src.core import config


class FeedEntry:
    __slots__ = ("stamp", "category", "text")

    def __init__(self, stamp: str, category: str, text: str):
        self.stamp = stamp
        self.category = category
        self.text = text

    def color(self) -> tuple:
        return config.FEED_CATEGORIES.get(self.category,
                                          (config.COLOR_TEXT, "?"))[0]

    def tag(self) -> str:
        return config.FEED_CATEGORIES.get(self.category,
                                          (None, "?"))[1]


class EventFeed:
    def __init__(self, cap: int = config.FEED_MAX_ENTRIES):
        self.cap = cap
        self.entries: list[FeedEntry] = []

    def add(self, stamp: str, category: str, text: str) -> None:
        self.entries.append(FeedEntry(stamp, category, text))
        if len(self.entries) > self.cap:
            self.entries.pop(0)

    def recent(self, n: int) -> list[FeedEntry]:
        return self.entries[-n:]

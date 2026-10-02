"""Radio messages worded by the model (display only).

The game always prints its own catalog text first.  When the model link is
on, the same message goes to the model to be worded like real radio
traffic; the answer, when it comes, is shown next to the original at the
radio stations.  Keyed by the message itself, bounded, never saved, and the
simulation never reads it.
"""

from __future__ import annotations

from collections import OrderedDict

from src.llm import prompts

MAX_STYLED = 48
MAX_PENDING = 6
MAX_CHARS = 420


def message_key(stamp, text: str) -> str:
    return f"{stamp}|{text}"


class RadioVoice:
    def __init__(self):
        self.styled: OrderedDict[str, str] = OrderedDict()
        self._pending: list = []

    def reset(self) -> None:
        self.styled.clear()
        self._pending.clear()

    def offer(self, service, language: str, side: str, key: str, original: str) -> bool:
        """Ask the model to word one message; False when it is not sent."""
        original = " ".join(str(original).split())
        if (not original or key in self.styled or len(self._pending) >= MAX_PENDING
                or any(row[0] == key for row in self._pending)):
            return False
        request = service.submit("radio", prompts.radio(language, side, original),
                                 max_tokens=160, temperature=0.5)
        if request is None:
            return False
        self._pending.append((key, request))
        return True

    def poll(self) -> int:
        """Collect finished answers; returns how many arrived."""
        done = 0
        still = []
        for key, request in self._pending:
            if not request.finished:
                still.append((key, request))
                continue
            if request.ok:
                text = request.text.strip()
                if len(text) > MAX_CHARS:
                    text = text[:MAX_CHARS - 1].rstrip() + "…"
                self.styled[key] = text
                self.styled.move_to_end(key)
                while len(self.styled) > MAX_STYLED:
                    self.styled.popitem(last=False)
                done += 1
        self._pending = still
        return done

    def get(self, key: str):
        return self.styled.get(key)

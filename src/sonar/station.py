"""A sonar workstation: one ``SonarSystem`` plus its operator state.

The frigate's workstation is what ``Game`` has always carried as flat
attributes (``game.sonar``, ``game.sonar_mode``, ``game.sonar_tools`` ...);
those names now delegate to the *active* station, which is the frigate's
except inside ``Game.sonar_perspective()``.  A crewed submarine gets its own
station, so the same operator methods, projections and views serve both
without either ever touching the other's contacts.

Everything here except what ``Game.save_state`` already writes for the
frigate is transient operator/UI state.
"""

from src.sonar import analysis_tools

# Game attribute names that live on the active station.
STATION_FIELDS = (
    "sonar", "sonar_mode", "sonar_page", "sonar_harmonic_hz", "sonar_tools",
    "tma_hypotheses", "tma_method", "selected_contact", "target",
    "sonar_display_palette", "sonar_display_black", "sonar_display_contrast",
    "sonar_display_history", "sonar_audio_enabled", "sonar_volume",
    "_sonar_audio_sequence", "_sonar_audio_suspended",
)


class SonarStation:
    """Operator state of one sonar workstation (frigate or crewed boat)."""

    def __init__(self, sonar=None, *, kind: str = "frigate", observer=None):
        self.kind = kind
        # The listening platform (``Ship`` or ``SubSonarPlatform``); ``None``
        # for the frigate, whose observer is always ``game.ship``.
        self.observer = observer
        # Callable: is this workstation out of action?  ``None`` for the
        # frigate, whose sonar room state lives in ``game.damage``.
        self.down = None
        self.sonar = sonar
        self.sonar_mode = "BOW"
        self.sonar_page = 0
        self.sonar_harmonic_hz = None
        # Operator LOFAR/DEMON tools: cursor, marks, integration (UI only).
        self.sonar_tools = analysis_tools.AcousticToolState()
        # Operator TMA hypotheses per sonar target (transient UI state).
        self.tma_hypotheses = {}
        # TMA page method: hypothesis/residuals, Ekelund range or dot stack.
        self.tma_method = "hypothesis"
        self.selected_contact = None
        self.target = None
        # Display-only CRT controls: no observation, simulation or save effect.
        self.sonar_display_palette = "green"
        self.sonar_display_black = 0.0
        self.sonar_display_contrast = 1.6
        self.sonar_display_history = 1.0
        self.sonar_audio_enabled = True
        self.sonar_volume = 0.5
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False


def _delegate(name):
    def get(game):
        try:
            station = game.__dict__["_sonar_ctx"]
        except KeyError:
            raise AttributeError(name) from None
        return getattr(station, name)

    def set_(game, value):
        station = game.__dict__.get("_sonar_ctx")
        if station is None:
            station = SonarStation()
            game.__dict__["_frigate_sonar"] = station
            game.__dict__["_sonar_ctx"] = station
        setattr(station, name, value)

    return property(get, set_, doc=f"Active sonar workstation's ``{name}``.")


def install_station_properties(cls) -> None:
    """Make ``cls`` (``Game``) delegate the station fields to ``_sonar_ctx``."""
    for name in STATION_FIELDS:
        setattr(cls, name, _delegate(name))

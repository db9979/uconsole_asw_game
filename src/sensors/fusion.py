"""Transient, operator-directed OPZ observations and display-only fusions."""

from dataclasses import dataclass
import math

from src.core import config


MAX_OPZ_FUSIONS = config.OPZ_FUSION_MAX
MIN_FUSION_MEMBERS = config.OPZ_FUSION_MEMBER_MIN
MAX_FUSION_MEMBERS = config.OPZ_FUSION_MEMBER_MAX


@dataclass(frozen=True)
class OPZObservation:
    observation_id: str
    source: str
    kind: str
    bearing: float
    range_nm: float | None
    x: float | None
    y: float | None
    course: float | None
    quality: float
    last_seen: float
    label: str
    classification: str | None = None
    bearing_uncertainty_deg: float | None = None
    position_seen: float | None = None
    jamming: bool = False
    members: tuple[str, ...] = ()
    depth_m: float | None = None
    speed_kn: float | None = None
    observer_x: float | None = None
    observer_y: float | None = None
    released_to_opz: bool = False
    altitude_m: float | None = None
    # Bridge lookout report (lookout_id label), never an operator annotation.
    visual: str | None = None
    # A fusion's member sensor sources (sorted, distinct); empty otherwise.
    sources: tuple[str, ...] = ()

    @property
    def track_id(self) -> str:
        return self.observation_id

    def __getitem__(self, key):
        aliases = {"track_id": "observation_id", "dist": "range_nm"}
        return getattr(self, aliases.get(key, key))

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


@dataclass(frozen=True)
class ManualFusion:
    fusion_id: str
    members: tuple[str, ...]
    classification: str | None = None
    # Formed by the OPZ's automatic correlation (``auto_fusion_plan``): it
    # keeps its identity while at least two member reports are current and
    # takes in further unambiguous reports; the operator can still dissolve it.
    auto: bool = False


def live_members(fusion: ManualFusion, current) -> tuple[str, ...] | None:
    """Member reports a fusion stands on now, or None when it has lapsed.

    A manual fusion needs every member; an automatic one the current members
    as long as at least two remain."""
    members = tuple(key for key in fusion.members if key in current)
    if fusion.auto:
        return members if len(members) >= MIN_FUSION_MEMBERS else None
    return members if len(members) == len(fusion.members) else None


class OPZFusionPicture:
    """Bounded transient OPZ workspace; it never mutates source pictures."""

    def __init__(self):
        self.fusions: dict[str, ManualFusion] = {}
        self.marked: set[str] = set()
        self.suppressed: set[str] = set()
        self.classifications: dict[str, str] = {}
        self.fusion_affiliations: dict[str, str] = {}
        self.show_suppressed = False
        self._sequence = 0
        # Dismissed correlation suggestions (pair keys, oldest first). Transient
        # like the fusions themselves: never saved, cleared with the picture.
        self.dismissed: dict[str, None] = {}

    def clear(self) -> None:
        self.fusions.clear()
        self.marked.clear()
        self.suppressed.clear()
        self.classifications.clear()
        self.fusion_affiliations.clear()
        self.show_suppressed = False
        self._sequence = 0
        self.dismissed.clear()

    def dismiss(self, key: str) -> None:
        self.dismissed.pop(key, None)
        self.dismissed[key] = None
        while len(self.dismissed) > config.OPZ_SUGGEST_DISMISSED_MAX:
            del self.dismissed[next(iter(self.dismissed))]

    def prune(self, observations) -> None:
        current = {item.observation_id for item in observations}
        self.marked.intersection_update(current)
        for key in [key for key in self.dismissed
                    if not set(key.split("+")) <= current]:
            del self.dismissed[key]
        self.suppressed.intersection_update(current | set(self.fusions))
        self.classifications = {key: value for key, value in self.classifications.items()
                                if key in current or key in self.fusions}
        for key, fusion in list(self.fusions.items()):
            # Automatic fusions shrink or lapse only in the simulation's own
            # correlation step (``auto_fuse``), never from a drawn frame.
            if not fusion.auto and not set(fusion.members) <= current:
                del self.fusions[key]
                self.fusion_affiliations.pop(key, None)

    def create(self, observations) -> ManualFusion | None:
        current = {item.observation_id for item in observations}
        members = tuple(sorted(self.marked & current))
        if (not MIN_FUSION_MEMBERS <= len(members) <= MAX_FUSION_MEMBERS
                or len(self.fusions) >= MAX_OPZ_FUSIONS):
            return None
        self._sequence += 1
        key = f"F-{self._sequence:02d}"
        fusion = ManualFusion(key, members)
        self.fusions[key] = fusion
        self.marked.clear()
        return fusion

    def dissolve(self, fusion_id: str) -> bool:
        if fusion_id not in self.fusions:
            return False
        # The operator separated these reports: automatic correlation must not
        # put them straight back together (the pairs count as dismissed).
        members = self.fusions[fusion_id].members
        for index, first in enumerate(members):
            for second in members[index + 1:]:
                self.dismiss(suggestion_key((first, second)))
        del self.fusions[fusion_id]
        self.suppressed.discard(fusion_id)
        self.classifications.pop(fusion_id, None)
        self.fusion_affiliations.pop(fusion_id, None)
        return True

    def computed(self, fusion: ManualFusion, observations, now: float,
                 stale_s: float) -> OPZObservation | None:
        by_id = {item.observation_id: item for item in observations}
        keys = live_members(fusion, by_id)
        if keys is None:
            return None
        members = [by_id[key] for key in keys]
        weights = [max(.001, item.display_quality(now, stale_s)) for item in members]
        positioned = [(item, weight) for item, weight in zip(members, weights)
                      if item.x is not None and item.y is not None]
        x = y = range_nm = position_seen = None
        if positioned:
            total = sum(weight for _, weight in positioned)
            x = sum(item.x * weight for item, weight in positioned) / total
            y = sum(item.y * weight for item, weight in positioned) / total
            position_seen = max(item.position_seen or item.last_seen
                                for item, _ in positioned)
        sx = sum(math.sin(math.radians(item.bearing)) * weight
                 for item, weight in zip(members, weights))
        sy = sum(math.cos(math.radians(item.bearing)) * weight
                 for item, weight in zip(members, weights))
        bearing = math.degrees(math.atan2(sx, sy)) % 360.0
        # Course and speed: quality-weighted over the members that report
        # them; a ship's own AIS course and speed over ground (satellite
        # navigation) stand alone, before the first noisy radar or lookout
        # estimates can swing the fused motion around.
        moving = list(zip(members, weights))
        broadcast = [(item, weight) for item, weight in moving
                     if item.source == "AIS" and item.course is not None]
        if broadcast:
            moving = broadcast
        steered = [(item, weight) for item, weight in moving
                   if item.course is not None]
        course = None
        if steered:
            cx = sum(math.sin(math.radians(item.course)) * weight for item, weight in steered)
            cy = sum(math.cos(math.radians(item.course)) * weight for item, weight in steered)
            if math.hypot(cx, cy) > 1e-9:
                course = math.degrees(math.atan2(cx, cy)) % 360.0
        timed = [(item, weight) for item, weight in moving
                 if item.speed_kn is not None]
        speed = (sum(item.speed_kn * weight for item, weight in timed)
                 / sum(weight for _, weight in timed)) if timed else None
        # The members' reported kind when they agree (an ESM or sonar report
        # carries none); an AIS member lends the fusion its broadcast name.
        kinds = {item.kind for item in members} - {"UNKNOWN"}
        kind = kinds.pop() if len(kinds) == 1 else "UNKNOWN"
        label = next((item.label for item in members if item.source == "AIS"),
                     fusion.fusion_id)
        return OPZObservation(
            fusion.fusion_id, "FUSION", kind, bearing, range_nm, x, y,
            course, sum(weights) / len(weights), max(item.last_seen for item in members),
            label, self.classifications.get(fusion.fusion_id),
            max((item.bearing_uncertainty_deg or 0.0) for item in members),
            position_seen, members=keys, speed_kn=speed,
            sources=tuple(sorted({item.source for item in members})))

    def visible(self, observations, now: float, stale_s: float):
        """The register: fused reports stand behind their fusion, so they are
        listed (like suppressed ones) only in the hidden view."""
        self.prune(observations)
        fused = [item for item in (self.computed(fusion, observations, now, stale_s)
                                   for fusion in self.fusions.values()) if item is not None]
        hidden = set(self.suppressed)
        hidden.update(member for item in fused for member in item.members)
        all_items = list(observations) + fused
        return tuple(sorted((item for item in all_items
                            if (item.observation_id in hidden)
                            == self.show_suppressed),
                            key=lambda item: item.observation_id))

    def auto_fuse(self, observations, own_x: float, own_y: float, now: float,
                  stale_s: float) -> tuple[str, ...]:
        """One automatic correlation step; returns the fusions it formed or
        extended. Pure in its inputs and the picture's own state."""
        current = {item.observation_id for item in observations}
        for key, fusion in list(self.fusions.items()):
            if not fusion.auto:
                continue
            members = live_members(fusion, current)
            if members is None:
                self.dissolve_lapsed(key)
            elif members != fusion.members:
                self.fusions[key] = ManualFusion(key, members, fusion.classification,
                                                 auto=True)
        autos = [(fusion, self.computed(fusion, observations, now, stale_s))
                 for _, fusion in sorted(self.fusions.items()) if fusion.auto]
        manual = {member for fusion in self.fusions.values() if not fusion.auto
                  for member in fusion.members}
        changed = []
        for target, members in auto_fusion_plan(
                observations, own_x, own_y, now,
                fusions=[(fusion, item) for fusion, item in autos if item is not None],
                excluded=manual, dismissed=self.dismissed):
            if target is None:
                if len(self.fusions) >= MAX_OPZ_FUSIONS:
                    continue
                self._sequence += 1
                target = f"F-{self._sequence:02d}"
                self.fusions[target] = ManualFusion(target, members, auto=True)
            else:
                old = self.fusions[target]
                self.fusions[target] = ManualFusion(target, members, old.classification,
                                                    auto=True)
            changed.append(target)
        return tuple(changed)

    def dissolve_lapsed(self, fusion_id: str) -> None:
        """Drop a fusion without dismissing its pairs (it lapsed)."""
        self.fusions.pop(fusion_id, None)
        self.suppressed.discard(fusion_id)
        self.classifications.pop(fusion_id, None)
        self.fusion_affiliations.pop(fusion_id, None)


# Display groups of OPZ report sources, in display order (``opz.source.*``
# names, ``opz.source_code.*`` one-letter register tags).
SOURCE_GROUPS = ("radar", "visual", "ais", "esm", "sonar", "helo", "buoy",
                 "mpa", "hfdf", "hoj", "datalink")


def source_group(source: str) -> str:
    """The display group of one report source string."""
    if source.startswith(("SONAR-DIP", "HELO")):
        return "helo"
    if source.startswith("SONAR-BUOY"):
        return "buoy"
    if source.startswith("SONAR-CONSORT"):
        return "datalink"
    if source.startswith("SONAR"):
        return "sonar"
    if source.startswith(("RADAR-MPA", "MPA-EYE")):
        return "mpa"
    if source.startswith("RADAR"):
        return "radar"
    if source.startswith("HFDF"):
        return "hfdf"
    return {"LOOKOUT": "visual", "AIS": "ais", "ESM": "esm",
            "HOJ": "hoj"}.get(source, "datalink")


def source_groups(observation) -> tuple[str, ...]:
    """Distinct display groups behind one register entry, in display order."""
    sources = observation.sources or (observation.source,)
    groups = {source_group(source) for source in sources}
    return tuple(group for group in SOURCE_GROUPS if group in groups)


def source_classification(observation_id: str, observations) -> str | None:
    """Look up an annotation using detached reports only, never producer labels."""
    return next((item.classification for item in observations
                 if item.observation_id == observation_id), None)


@dataclass(frozen=True)
class CorrelationSuggestion:
    """A candidate pairing of two published reports; never applied by itself."""
    key: str
    members: tuple[str, str]
    bearing: float
    bearing_delta_deg: float
    distance_nm: float | None
    score: float
    course_delta_deg: float | None = None
    speed_delta_kn: float | None = None
    class_match: bool | None = None


# Sensor families whose reports may be suggested together (different families
# only). Remote reports (buoys, dipping sonar, helicopter MAD), home-on-jam
# strobes, datalinked own weapons and fusions are never suggested.
_REMOTE_PREFIXES = ("SONAR-BUOY", "SONAR-DIP", "SONAR-CONSORT", "HELO")
_AIR_KINDS = ("FLG", "ASM", "AIR", "HELO")


def suggestion_key(members) -> str:
    return "+".join(sorted(members))


def _sensor_family(observation) -> str | None:
    source = observation.source
    if source.startswith(_REMOTE_PREFIXES):
        return None
    if source.startswith("SONAR"):
        return "SONAR"
    if source.startswith("RADAR"):
        return "RADAR"
    if source == "ESM":
        return "ESM"
    if source == "LOOKOUT":
        return "VISUAL"
    if source == "AIS":
        return "AIS"
    return None


# Operator classes an AIS transmitter (a declared merchant) can never be.
_NOT_AIS_CLASSES = ("U_BOOT", "BIOLOGISCH", "FLUGZEUG")


def _motion_terms(first, second):
    """(course delta, speed delta, score terms) of two reports, or None when
    their motion rules the pairing out. Terms are fractions of their gates."""
    terms = []
    course_delta = speed_delta = None
    speeds = [item.speed_kn for item in (first, second) if item.speed_kn is not None]
    moving = not speeds or max(speeds) >= config.OPZ_SUGGEST_MIN_SPEED_KN
    if first.course is not None and second.course is not None and moving:
        course_delta = abs(config.angle_diff_deg(first.course, second.course))
        if course_delta > config.OPZ_SUGGEST_COURSE_DEG:
            return None
        terms.append(course_delta / config.OPZ_SUGGEST_COURSE_DEG)
    if first.speed_kn is not None and second.speed_kn is not None:
        speed_delta = abs(first.speed_kn - second.speed_kn)
        gate = (config.OPZ_SUGGEST_SPEED_KN
                + config.OPZ_SUGGEST_SPEED_SHARE * max(first.speed_kn, second.speed_kn))
        if speed_delta > gate:
            return None
        terms.append(speed_delta / gate)
    return course_delta, speed_delta, terms


def _class_match(first, family_a, second, family_b):
    """True/False for two classified reports, None when unknown; "reject"
    when their signatures cannot belong to one contact."""
    for item, other_family in ((first, family_b), (second, family_a)):
        if other_family == "AIS" and item.classification in _NOT_AIS_CLASSES:
            return "reject"
    if first.classification is None or second.classification is None:
        return None
    if first.classification != second.classification:
        return "reject"
    return True


def _own_bearing(observation, own_x: float, own_y: float, observer_nm: float):
    """Bearing (and position) of a report as seen from the frigate, or None."""
    if observation.x is not None and observation.y is not None:
        dx, dy = observation.x - own_x, observation.y - own_y
        return (math.degrees(math.atan2(dx, -dy)) % 360.0,
                (observation.x, observation.y), math.hypot(dx, dy))
    if (observation.observer_x is not None and observation.observer_y is not None
            and math.hypot(observation.observer_x - own_x,
                           observation.observer_y - own_y) > observer_nm):
        return None
    return observation.bearing % 360.0, None, None


def _candidate(item, own_x: float, own_y: float, now: float):
    """(report, family, bearing, position, range) of a comparable report."""
    family = _sensor_family(item)
    max_age = (config.OPZ_SUGGEST_AIS_MAX_AGE_S if family == "AIS"
               else config.OPZ_SUGGEST_MAX_AGE_S)
    if family is None or not 0.0 <= now - item.last_seen <= max_age:
        return None
    geometry = _own_bearing(item, own_x, own_y, config.OPZ_SUGGEST_OBSERVER_NM)
    if geometry is None:
        return None
    return (item, family, *geometry)


def _compatible(first, family_a, second, family_b):
    """Class match (True/None) of two reports of different sensors, or
    "reject" when domain or signature rules them out."""
    if family_a == family_b:
        return "reject"
    if ("SONAR" in (family_a, family_b) or "AIS" in (family_a, family_b)) and (
            first.kind in _AIR_KINDS or second.kind in _AIR_KINDS):
        return "reject"
    return _class_match(first, family_a, second, family_b)


def _score(first, bearing_a, pos_a, range_a, second, bearing_b, pos_b, range_b):
    """(mean bearing, bearing delta, distance, score, course delta, speed
    delta) of two reports inside every gate, or None."""
    unc_a = (first.bearing_uncertainty_deg
             if first.bearing_uncertainty_deg is not None
             else config.OPZ_SUGGEST_BEARING_DEFAULT_UNC_DEG)
    unc_b = (second.bearing_uncertainty_deg
             if second.bearing_uncertainty_deg is not None
             else config.OPZ_SUGGEST_BEARING_DEFAULT_UNC_DEG)
    gate = min(config.OPZ_SUGGEST_BEARING_MAX_DEG,
               config.OPZ_SUGGEST_BEARING_BASE_DEG + math.hypot(unc_a, unc_b))
    delta = abs(config.angle_diff_deg(bearing_a, bearing_b))
    if delta > gate:
        return None
    score = delta / gate
    distance = None
    if pos_a is not None and pos_b is not None:
        distance = math.hypot(pos_a[0] - pos_b[0], pos_a[1] - pos_b[1])
        position_gate = (config.OPZ_SUGGEST_POSITION_NM
                         + config.OPZ_SUGGEST_POSITION_RANGE_SHARE
                         * min(range_a, range_b))
        if distance > position_gate:
            return None
        score = .5 * (score + distance / position_gate)
    motion = _motion_terms(first, second)
    if motion is None:
        return None
    course_delta, speed_delta, terms = motion
    if terms:
        score = (score + sum(terms)) / (1 + len(terms))
    mean = math.degrees(math.atan2(
        math.sin(math.radians(bearing_a)) + math.sin(math.radians(bearing_b)),
        math.cos(math.radians(bearing_a)) + math.cos(math.radians(bearing_b))
    )) % 360.0
    return mean, delta, distance, score, course_delta, speed_delta


def suggest_correlations(observations, own_x: float, own_y: float, now: float, *,
                         fused=(), dismissed=(), limit: int | None = None,
                         ) -> tuple[CorrelationSuggestion, ...]:
    """Suggest cross-sensor pairings from detached OPZ reports only.

    Pure and bounded: the same reports, own position and time always give the
    same suggestions in the same order. Each report appears in at most one
    suggestion; reports already fused and dismissed pairings are skipped.
    """
    limit = config.OPZ_SUGGEST_MAX if limit is None else limit
    fused = set(fused)
    dismissed = set(dismissed)
    candidates = [row for row in (_candidate(item, own_x, own_y, now)
                                  for item in observations
                                  if item.observation_id not in fused)
                  if row is not None]
    candidates.sort(key=lambda row: (-row[0].last_seen, row[0].observation_id))
    del candidates[config.OPZ_SUGGEST_CANDIDATES_MAX:]
    candidates.sort(key=lambda row: row[0].observation_id)
    pairs = []
    for index, (first, family_a, bearing_a, pos_a, range_a) in enumerate(candidates):
        for second, family_b, bearing_b, pos_b, range_b in candidates[index + 1:]:
            if family_a == family_b:
                continue
            key = suggestion_key((first.observation_id, second.observation_id))
            if key in dismissed:
                continue
            class_match = _compatible(first, family_a, second, family_b)
            if class_match == "reject":
                continue
            scored = _score(first, bearing_a, pos_a, range_a,
                            second, bearing_b, pos_b, range_b)
            if scored is None:
                continue
            mean, delta, distance, score, course_delta, speed_delta = scored
            if class_match is True:
                score *= config.OPZ_SUGGEST_CLASS_BONUS
            pairs.append(CorrelationSuggestion(
                key, tuple(sorted((first.observation_id, second.observation_id))),
                mean, delta, distance, round(score, 9), course_delta, speed_delta,
                class_match))
    pairs.sort(key=lambda item: (item.score, item.key))
    chosen, used = [], set()
    for pair in pairs:
        if len(chosen) >= limit:
            break
        if used.intersection(pair.members):
            continue
        used.update(pair.members)
        chosen.append(pair)
    return tuple(chosen)


def auto_fusion_plan(observations, own_x: float, own_y: float, now: float, *,
                     fusions=(), excluded=(), dismissed=()):
    """Unambiguous cross-sensor matches the OPZ fuses by itself.

    ``fusions`` are the current automatic fusions with their computed report.
    Returns ``(fusion_id or None, members)`` steps: a new fusion of two
    reports, or one more report joining an existing fusion. A match counts
    only when at least one side has a position fix, its score is inside
    ``OPZ_AUTO_FUSE_SCORE_MAX`` and neither side has another candidate from
    the same sensor family (so two ships close together stay apart and appear
    as a suggestion instead). Pure: same inputs, same plan.
    """
    dismissed = set(dismissed)
    by_id = {item.observation_id: item for item in observations}
    taken = set(excluded)
    units = []
    for fusion, item in fusions:
        reports = [by_id[key] for key in item.members if key in by_id]
        families = {_sensor_family(report) for report in reports}
        taken.update(fusion.members)
        if None in families or len(reports) != len(item.members):
            continue
        geometry = _own_bearing(item, own_x, own_y, config.OPZ_SUGGEST_OBSERVER_NM)
        if geometry is None or not 0.0 <= now - item.last_seen <= config.OPZ_SUGGEST_MAX_AGE_S:
            continue
        units.append((fusion.fusion_id, fusion.fusion_id, tuple(reports),
                      frozenset(families), item, *geometry))
    raw = [row for row in (_candidate(item, own_x, own_y, now)
                           for item in observations if item.observation_id not in taken)
           if row is not None]
    raw.sort(key=lambda row: (-row[0].last_seen, row[0].observation_id))
    del raw[config.OPZ_SUGGEST_CANDIDATES_MAX:]
    for item, family, *geometry in sorted(raw, key=lambda row: row[0].observation_id):
        units.append((item.observation_id, None, (item,), frozenset((family,)),
                      item, *geometry))
    units.sort(key=lambda unit: unit[0])
    gated = []
    for index, first in enumerate(units):
        for second in units[index + 1:]:
            if first[1] is not None and second[1] is not None:
                continue
            if first[3] & second[3] or (first[6] is None and second[6] is None):
                continue
            if len(first[2]) + len(second[2]) > MAX_FUSION_MEMBERS:
                continue
            verdicts = [_compatible(a, _sensor_family(a), b, _sensor_family(b))
                        for a in first[2] for b in second[2]]
            if "reject" in verdicts or any(
                    suggestion_key((a.observation_id, b.observation_id)) in dismissed
                    for a in first[2] for b in second[2]):
                continue
            scored = _score(first[4], first[5], first[6], first[7],
                            second[4], second[5], second[6], second[7])
            if scored is None:
                continue
            score = scored[3]
            if True in verdicts:
                score *= config.OPZ_SUGGEST_CLASS_BONUS
            gated.append((score, first, second))
    partners = {}
    for _, first, second in gated:
        partners.setdefault(first[0], []).append(second)
        partners.setdefault(second[0], []).append(first)

    def unique(unit, other) -> bool:
        return not any(item[0] != other[0] and item[3] & other[3]
                       for item in partners[unit[0]])

    plan, used = [], set()
    for score, first, second in sorted(gated, key=lambda row: (
            row[0], row[1][0], row[2][0])):
        if (score > config.OPZ_AUTO_FUSE_SCORE_MAX or first[0] in used
                or second[0] in used or not unique(first, second)
                or not unique(second, first)):
            continue
        used.update((first[0], second[0]))
        target = first[1] if first[1] is not None else second[1]
        members = tuple(sorted(report.observation_id
                               for report in (*first[2], *second[2])))
        plan.append((target, members))
    return tuple(plan)


def chart_family(source: str) -> str:
    """The sensor family a chart report comes from (its source when the
    report is relayed from another platform)."""
    if source.startswith("RADAR"):
        return "RADAR"
    if source == "LOOKOUT":
        return "VISUAL"
    if source.startswith("SONAR"):
        return "SONAR"
    return source


def _chart_domains_agree(first: str, second: str) -> bool:
    surface = ("SURFACE", "AIS")
    return (first == second or "UNKNOWN" in (first, second)
            or (first in surface and second in surface))


def merge_chart_reports(items) -> dict:
    """Reports a chart draws as one contact although the OPZ has not fused
    them (yet): a ship the radar and the lookout both report right on top
    of each other while their first motion estimates still disagree.

    ``items`` are dicts with ``key``, ``families`` (sensor families the
    report or fusion stands for), ``domain``, ``x``, ``y``, ``range_nm``
    (from the own ship), ``fused`` and ``quality``. Two reports are one
    contact when they lie inside ``CHART_SAME_CONTACT_NM`` (plus
    ``CHART_SAME_CONTACT_RANGE_SHARE`` of the range), share no sensor
    family (two radar echoes stay two ships), agree in domain, and neither
    has a second such neighbour from the other's family (two ships close
    together stay apart). Fusions and better reports lead. Display only and
    pure: returns ``{joined key: lead key}``."""
    order = sorted(items, key=lambda item: (not item["fused"], -float(item["quality"] or 0.0),
                                            str(item["key"])))
    rank = {item["key"]: index for index, item in enumerate(order)}

    def near(first, second) -> float | None:
        if first["families"] & second["families"] or not _chart_domains_agree(
                first["domain"], second["domain"]):
            return None
        gate = config.CHART_SAME_CONTACT_NM + config.CHART_SAME_CONTACT_RANGE_SHARE * max(
            float(first["range_nm"] or 0.0), float(second["range_nm"] or 0.0))
        distance = math.hypot(first["x"] - second["x"], first["y"] - second["y"])
        return distance if distance <= gate else None

    neighbours = {item["key"]: [] for item in order}
    edges = []
    for index, first in enumerate(order):
        for second in order[index + 1:]:
            distance = near(first, second)
            if distance is not None:
                neighbours[first["key"]].append(second)
                neighbours[second["key"]].append(first)
                edges.append((distance, first, second))

    def unique(item, partner) -> bool:
        return not any(other["key"] != partner["key"]
                       and other["families"] & partner["families"]
                       for other in neighbours[item["key"]])

    group = {item["key"]: item["key"] for item in order}
    families = {item["key"]: set(item["families"]) for item in order}

    def root(key):
        while group[key] != key:
            key = group[key]
        return key

    for _distance, first, second in sorted(edges, key=lambda edge: (
            edge[0], rank[edge[1]["key"]], rank[edge[2]["key"]])):
        if not (unique(first, second) and unique(second, first)):
            continue
        a, b = root(first["key"]), root(second["key"])
        if a == b or families[a] & families[b]:
            continue
        lead, other = (a, b) if rank[a] < rank[b] else (b, a)
        group[other] = lead
        families[lead] |= families.pop(other)
    return {key: root(key) for key in group if root(key) != key}

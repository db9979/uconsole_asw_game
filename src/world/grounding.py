"""Pure bounded hull-footprint and swept grounding queries.

All dimensions are fictional U-Jagd gameplay assumptions.  This module is
deliberately independent from acoustic propagation and sonar terrain queries.
"""

from dataclasses import dataclass
import math


METRES_PER_NM = 1852.0
_EPSILON_NM = 1e-10
_MAX_SWEEP_SAMPLES = 2048
_BISECTION_STEPS = 48
_TURN_SWEEP_LIMIT = 8192


@dataclass(frozen=True)
class HullSpec:
    mass_t: float = 3600.0
    length_m: float = 118.0
    beam_m: float = 14.0
    draft_m: float = 7.5
    keel_reserve_m: float = 1.5

    def __post_init__(self) -> None:
        values = (self.mass_t, self.length_m, self.beam_m, self.draft_m,
                  self.keel_reserve_m)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("hull assumptions must be positive finite numbers")

    @property
    def minimum_depth_m(self) -> float:
        return self.draft_m + self.keel_reserve_m

    def to_dict(self) -> dict:
        return {"mass_t": self.mass_t, "length_m": self.length_m,
                "beam_m": self.beam_m, "draft_m": self.draft_m,
                "keel_reserve_m": self.keel_reserve_m}


DEFAULT_HULL_SPEC = HullSpec()


@dataclass(frozen=True)
class GroundingContact:
    kind: str
    x_nm: float
    y_nm: float
    normal_x: float
    normal_y: float
    hull_longitudinal: float
    hull_lateral: float


@dataclass(frozen=True)
class GroundingSweep:
    contacted: bool
    safe_x_nm: float
    safe_y_nm: float
    safe_course_deg: float
    contact: GroundingContact | None = None
    fraction: float = 1.0
    query_count: int = 0


def _hull_points(x_nm: float, y_nm: float, course_deg: float,
                 hull: HullSpec) -> tuple[tuple[float, float, float, float], ...]:
    angle = math.radians(course_deg)
    forward = (math.sin(angle), -math.cos(angle))
    starboard = (math.cos(angle), math.sin(angle))
    half_length = hull.length_m / (2.0 * METRES_PER_NM)
    half_beam = hull.beam_m / (2.0 * METRES_PER_NM)
    points = []
    # Corners, edge midpoints and centre bound work while making dimensions
    # materially affect both shoreline and shallow-water contact.
    for longitudinal, lateral in ((1, -1), (1, 0), (1, 1),
                                  (0, -1), (0, 0), (0, 1),
                                  (-1, -1), (-1, 0), (-1, 1)):
        px = (x_nm + forward[0] * half_length * longitudinal
              + starboard[0] * half_beam * lateral)
        py = (y_nm + forward[1] * half_length * longitudinal
              + starboard[1] * half_beam * lateral)
        points.append((px, py, float(longitudinal), float(lateral)))
    return tuple(points)


def _segments_intersect(first, second, third, fourth) -> tuple[float, float] | None:
    dx, dy = second[0] - first[0], second[1] - first[1]
    ex, ey = fourth[0] - third[0], fourth[1] - third[1]
    cross = dx * ey - dy * ex
    if abs(cross) <= _EPSILON_NM:
        return None
    qx, qy = third[0] - first[0], third[1] - first[1]
    t = (qx * ey - qy * ex) / cross
    u = (qx * dy - qy * dx) / cross
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return first[0] + dx * t, first[1] + dy * t
    return None


def _convex_hull(points):
    points = sorted(set(points))
    if len(points) <= 2:
        return tuple(points)

    def cross(origin, first, second):
        return ((first[0] - origin[0]) * (second[1] - origin[1])
                - (first[1] - origin[1]) * (second[0] - origin[0]))

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _point_in_convex(point, polygon):
    sign = 0
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        value = ((second[0] - first[0]) * (point[1] - first[1])
                 - (second[1] - first[1]) * (point[0] - first[0]))
        if abs(value) <= _EPSILON_NM:
            continue
        current = 1 if value > 0.0 else -1
        if sign and current != sign:
            return False
        sign = current
    return True


def _point_in_polygon(point, polygon):
    inside = False
    x, y = point
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        if (first[1] > y) != (second[1] > y):
            crossing_x = (first[0] + (y - first[1])
                          * (second[0] - first[0]) / (second[1] - first[1]))
            if x < crossing_x:
                inside = not inside
    return inside


def _point_segment_distance(point, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length2 = dx * dx + dy * dy
    if length2 <= _EPSILON_NM * _EPSILON_NM:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    t = max(0.0, min(1.0, ((point[0] - first[0]) * dx
                            + (point[1] - first[1]) * dy) / length2))
    return math.hypot(point[0] - first[0] - t * dx,
                      point[1] - first[1] - t * dy)


def _polygons_within(first, second, distance):
    if any(_point_in_convex(point, first) for point in second):
        return True
    if any(_point_in_polygon(point, second) for point in first):
        return True
    for first_index, first_start in enumerate(first):
        first_end = first[(first_index + 1) % len(first)]
        for second_index, second_start in enumerate(second):
            second_end = second[(second_index + 1) % len(second)]
            if _segments_intersect(first_start, first_end,
                                   second_start, second_end) is not None:
                return True
            if distance > 0.0 and min(
                    _point_segment_distance(first_start, second_start, second_end),
                    _point_segment_distance(first_end, second_start, second_end),
                    _point_segment_distance(second_start, first_start, first_end),
                    _point_segment_distance(second_end, first_start, first_end)) <= distance:
                return True
    return False


def _land_normal(world, x, y):
    best = None
    for land_index, landmass in enumerate(world.coast.landmasses):
        for edge_index, first in enumerate(landmass.points):
            second = landmass.points[(edge_index + 1) % len(landmass.points)]
            dx, dy = second[0] - first[0], second[1] - first[1]
            length2 = dx * dx + dy * dy
            if length2 <= _EPSILON_NM * _EPSILON_NM:
                continue
            t = max(0.0, min(1.0, ((x - first[0]) * dx
                                    + (y - first[1]) * dy) / length2))
            nearest = (first[0] + t * dx, first[1] + t * dy)
            distance = math.hypot(x - nearest[0], y - nearest[1])
            candidate = (distance, land_index, edge_index, nearest, dx, dy)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        return 1.0, 0.0
    distance, _, _, nearest, dx, dy = best
    if distance > _EPSILON_NM:
        return ((nearest[0] - x) / distance, (nearest[1] - y) / distance)
    length = math.hypot(dx, dy)
    first = (-dy / length, dx / length)
    probe = 1e-7
    if world.on_land(x + first[0] * probe, y + first[1] * probe):
        return -first[0], -first[1]
    return first


def _turning_region(world, pose, t0, t1, hull):
    first = pose(t0)
    second = pose(t1)
    first_corners = _hull_points(*first, hull)
    second_corners = _hull_points(*second, hull)
    corners = (first_corners[0], first_corners[2], first_corners[8], first_corners[6],
               second_corners[0], second_corners[2], second_corners[8], second_corners[6])
    region = _convex_hull(tuple(point[:2] for point in corners))
    angle = abs(((second[2] - first[2] + 180.0) % 360.0) - 180.0)
    radius = math.hypot(hull.length_m, hull.beam_m) / (2.0 * METRES_PER_NM)
    sagitta = radius * (1.0 - math.cos(math.radians(angle) * 0.5))
    bounds = (min(point[0] for point in region) - sagitta,
              min(point[1] for point in region) - sagitta,
              max(point[0] for point in region) + sagitta,
              max(point[1] for point in region) + sagitta)
    boundary = (bounds[0] < 0.0 or bounds[1] < 0.0
                or bounds[2] > world.size_nm or bounds[3] > world.size_nm)
    land = False
    for landmass in world.coast.landmasses:
        if (landmass.bounds[2] + sagitta < bounds[0]
                or landmass.bounds[3] + sagitta < bounds[1]
                or landmass.bounds[0] - sagitta > bounds[2]
                or landmass.bounds[1] - sagitta > bounds[3]):
            continue
        if _polygons_within(region, landmass.points, sagitta):
            land = True
            break
    return boundary or land


def _conservative_turn_contact(world, start, end, hull, pose):
    """Narrow the earliest contact in a conservative rotating-hull envelope."""
    stack = [(0.0, 1.0, 0)]
    visited = 0
    while stack and visited < _TURN_SWEEP_LIMIT:
        low, high, depth = stack.pop()
        visited += 1
        if not _turning_region(world, pose, low, high, hull):
            continue
        centre_span = math.hypot((end[0] - start[0]) * (high - low),
                                 (end[1] - start[1]) * (high - low))
        angle = abs(((end[2] - start[2] + 180.0) % 360.0) - 180.0)
        radius = math.hypot(hull.length_m, hull.beam_m) / (2.0 * METRES_PER_NM)
        uncertainty = centre_span + radius * math.radians(angle) * (high - low)
        if depth >= _BISECTION_STEPS or uncertainty <= _EPSILON_NM:
            for fraction in (high, (low + high) * 0.5, low):
                contact = grounding_contact(world, *pose(fraction), hull)
                if contact is not None and contact.kind in ("land", "boundary"):
                    return fraction, 0, contact
            # The envelope's maximum overreach is below the physical tolerance.
            continue
        middle = (low + high) * 0.5
        stack.append((middle, high, depth + 1))
        stack.append((low, middle, depth + 1))
    return None


def _exact_translational_land_contact(world, start, end, hull):
    """Exact constant-heading rectangle sweep against coastline polygons."""
    if abs(((end[2] - start[2] + 180.0) % 360.0) - 180.0) > _EPSILON_NM:
        return None
    sx, sy, course = start
    ex, ey, _ = end
    dx, dy = ex - sx, ey - sy
    if abs(dx) <= _EPSILON_NM and abs(dy) <= _EPSILON_NM:
        return None
    start_points = _hull_points(sx, sy, course, hull)
    end_points = _hull_points(ex, ey, course, hull)
    candidates = []
    for index, (first, second) in enumerate(zip(start_points, end_points)):
        crossing = world.coast.first_physical_land_intersection(
            first[:2], second[:2])
        if crossing is not None:
            t, x, y, nx, ny = crossing
            candidates.append((t, index, GroundingContact(
                "land", x, y, nx, ny, first[2], first[3])))

    angle = math.radians(course)
    forward = (math.sin(angle), -math.cos(angle))
    starboard = (math.cos(angle), math.sin(angle))
    half_length = hull.length_m / (2.0 * METRES_PER_NM)
    half_beam = hull.beam_m / (2.0 * METRES_PER_NM)
    velocity = ((dx * forward[0] + dy * forward[1]) / half_length,
                (dx * starboard[0] + dy * starboard[1]) / half_beam)

    def inside_interval(position, delta):
        if abs(delta) <= _EPSILON_NM:
            return (0.0, 1.0) if -1.0 <= position <= 1.0 else None
        first_t, second_t = (-1.0 - position) / delta, (1.0 - position) / delta
        return max(0.0, min(first_t, second_t)), min(1.0, max(first_t, second_t))

    vertex_index = len(start_points)
    swept_bounds = (
        min(point[0] for point in start_points + end_points),
        min(point[1] for point in start_points + end_points),
        max(point[0] for point in start_points + end_points),
        max(point[1] for point in start_points + end_points),
    )
    for landmass in world.coast.landmasses:
        if (landmass.bounds[2] < swept_bounds[0]
                or landmass.bounds[3] < swept_bounds[1]
                or landmass.bounds[0] > swept_bounds[2]
                or landmass.bounds[1] > swept_bounds[3]):
            vertex_index += len(landmass.points)
            continue
        for vx, vy in landmass.points:
            relative_x, relative_y = vx - sx, vy - sy
            longitudinal = (relative_x * forward[0] + relative_y * forward[1]) \
                / half_length
            lateral = (relative_x * starboard[0] + relative_y * starboard[1]) \
                / half_beam
            lon_interval = inside_interval(longitudinal, -velocity[0])
            lat_interval = inside_interval(lateral, -velocity[1])
            if lon_interval is None or lat_interval is None:
                vertex_index += 1
                continue
            enter = max(lon_interval[0], lat_interval[0])
            leave = min(lon_interval[1], lat_interval[1])
            if enter <= leave and 0.0 <= enter <= 1.0:
                local_long = longitudinal - velocity[0] * enter
                local_lat = lateral - velocity[1] * enter
                speed = math.hypot(dx, dy)
                nx, ny = (-dx / speed, -dy / speed)
                candidates.append((enter, vertex_index, GroundingContact(
                    "land", vx, vy, nx, ny, local_long, local_lat)))
            vertex_index += 1
    return min(candidates, key=lambda item: (item[0], item[1])) if candidates else None


def grounding_contact(world, x_nm: float, y_nm: float, course_deg: float,
                      hull: HullSpec = DEFAULT_HULL_SPEC) -> GroundingContact | None:
    """Return the stable highest-priority physical contact for one hull pose."""
    if not all(math.isfinite(value) for value in (x_nm, y_nm, course_deg)):
        raise ValueError("hull pose must be finite")
    points = _hull_points(x_nm, y_nm, course_deg, hull)
    size = world.size_nm
    for px, py, longitudinal, lateral in points:
        if px < 0.0 or px > size or py < 0.0 or py > size:
            nx = 1.0 if px < 0.0 else -1.0 if px > size else 0.0
            ny = 1.0 if py < 0.0 else -1.0 if py > size else 0.0
            return GroundingContact("boundary", px, py, nx, ny,
                                    longitudinal, lateral)
    for px, py, longitudinal, lateral in points:
        if world.on_land(px, py):
            delta = max(min(hull.beam_m, hull.length_m) / METRES_PER_NM / 4.0,
                        1e-5)
            nx = float(world.on_land(px - delta, py)) - float(
                world.on_land(px + delta, py))
            ny = float(world.on_land(px, py - delta)) - float(
                world.on_land(px, py + delta))
            length = math.hypot(nx, ny)
            if length:
                nx, ny = nx / length, ny / length
            else:
                nx, ny = _land_normal(world, px, py)
            return GroundingContact("land", px, py, nx, ny,
                                    longitudinal, lateral)
    corners = (points[0], points[2], points[8], points[6])
    angle = math.radians(course_deg)
    forward = (math.sin(angle), -math.cos(angle))
    starboard = (math.cos(angle), math.sin(angle))
    half_length = hull.length_m / (2.0 * METRES_PER_NM)
    half_beam = hull.beam_m / (2.0 * METRES_PER_NM)
    hull_bounds = (min(point[0] for point in corners),
                   min(point[1] for point in corners),
                   max(point[0] for point in corners),
                   max(point[1] for point in corners))
    for landmass in world.coast.landmasses:
        if (landmass.bounds[2] < hull_bounds[0]
                or landmass.bounds[0] > hull_bounds[2]
                or landmass.bounds[3] < hull_bounds[1]
                or landmass.bounds[1] > hull_bounds[3]):
            continue
        for lx, ly in landmass.points:
            dx, dy = lx - x_nm, ly - y_nm
            longitudinal = (dx * forward[0] + dy * forward[1]) / half_length
            lateral = (dx * starboard[0] + dy * starboard[1]) / half_beam
            if abs(longitudinal) <= 1.0 and abs(lateral) <= 1.0:
                nx, ny = _land_normal(world, lx, ly)
                return GroundingContact("land", lx, ly, nx, ny,
                                        longitudinal, lateral)
        for index, corner in enumerate(corners):
            hull_edge = (corner[:2], corners[(index + 1) % 4][:2])
            for edge_index, edge_first in enumerate(landmass.points):
                edge_second = landmass.points[(edge_index + 1) % len(landmass.points)]
                crossing = _segments_intersect(*hull_edge, edge_first, edge_second)
                if crossing is not None:
                    dx, dy = crossing[0] - x_nm, crossing[1] - y_nm
                    longitudinal = (dx * forward[0] + dy * forward[1]) / half_length
                    lateral = (dx * starboard[0] + dy * starboard[1]) / half_beam
                    nx, ny = _land_normal(world, *crossing)
                    return GroundingContact("land", *crossing, nx, ny,
                                            longitudinal, lateral)
    if world.coast.has_bathymetry:
        depth, px, py = world.coast.minimum_physical_depth_in_polygon(
            tuple(point[:2] for point in corners))
        if depth <= hull.minimum_depth_m:
            delta = max(min(hull.beam_m, hull.length_m) / METRES_PER_NM / 4.0,
                        1e-5)
            nx = (world.physical_depth_m(px + delta, py)
                  - world.physical_depth_m(px - delta, py))
            ny = (world.physical_depth_m(px, py + delta)
                  - world.physical_depth_m(px, py - delta))
            length = math.hypot(nx, ny)
            if length:
                nx, ny = nx / length, ny / length
            else:
                offset_length = math.hypot(px - x_nm, py - y_nm)
                if offset_length:
                    nx, ny = ((x_nm - px) / offset_length,
                              (y_nm - py) / offset_length)
                else:
                    nx, ny = 1.0, 0.0
            offset_x, offset_y = px - x_nm, py - y_nm
            longitudinal = (offset_x * forward[0] + offset_y * forward[1]) / half_length
            lateral = (offset_x * starboard[0] + offset_y * starboard[1]) / half_beam
            return GroundingContact("shallow", px, py, nx, ny,
                                    longitudinal, lateral)
    return None


def hull_is_safe(world, x_nm: float, y_nm: float, course_deg: float,
                 hull: HullSpec = DEFAULT_HULL_SPEC) -> bool:
    return grounding_contact(world, x_nm, y_nm, course_deg, hull) is None


def grounding_contact_is_consistent(world, pose, hull, contact) -> bool:
    """Validate persisted contact evidence without changing simulation state."""
    tolerance_nm = 1e-6
    normal_length = math.hypot(contact.normal_x, contact.normal_y)
    if not math.isfinite(normal_length) or abs(normal_length - 1.0) > 1e-6:
        return False
    if grounding_contact(world, *pose, hull) is not None:
        return False

    angle = math.radians(pose[2])
    forward = (math.sin(angle), -math.cos(angle))
    starboard = (math.cos(angle), math.sin(angle))
    half_length = hull.length_m / (2.0 * METRES_PER_NM)
    half_beam = hull.beam_m / (2.0 * METRES_PER_NM)
    expected_x = (pose[0] + forward[0] * half_length * contact.hull_longitudinal
                  + starboard[0] * half_beam * contact.hull_lateral)
    expected_y = (pose[1] + forward[1] * half_length * contact.hull_longitudinal
                  + starboard[1] * half_beam * contact.hull_lateral)
    if math.hypot(contact.x_nm - expected_x,
                  contact.y_nm - expected_y) > tolerance_nm:
        return False

    if contact.kind == "boundary":
        candidates = (
            (contact.x_nm <= tolerance_nm and contact.normal_x > .999999),
            (contact.x_nm >= world.size_nm - tolerance_nm
             and contact.normal_x < -.999999),
            (contact.y_nm <= tolerance_nm and contact.normal_y > .999999),
            (contact.y_nm >= world.size_nm - tolerance_nm
             and contact.normal_y < -.999999),
        )
        return any(candidates)
    if not (0.0 <= contact.x_nm <= world.size_nm
            and 0.0 <= contact.y_nm <= world.size_nm):
        return False
    if contact.kind == "land":
        nearest = float("inf")
        for landmass in world.coast.landmasses:
            for index, first in enumerate(landmass.points):
                second = landmass.points[(index + 1) % len(landmass.points)]
                nearest = min(nearest, _point_segment_distance(
                    (contact.x_nm, contact.y_nm), first, second))
        expected_normal = _land_normal(world, contact.x_nm, contact.y_nm)
        normal_alignment = (contact.normal_x * expected_normal[0]
                            + contact.normal_y * expected_normal[1])
        return nearest <= tolerance_nm and normal_alignment >= .999999
    if contact.kind == "shallow":
        return (world.coast.has_bathymetry
                and not world.on_land(contact.x_nm, contact.y_nm)
                and world.physical_depth_m(contact.x_nm, contact.y_nm)
                <= hull.minimum_depth_m + 1e-6)
    return False


def swept_grounding(world, start: tuple[float, float, float],
                    end: tuple[float, float, float],
                    hull: HullSpec = DEFAULT_HULL_SPEC) -> GroundingSweep:
    """Find earliest contact and the last safe pose with bounded deterministic work."""
    sx, sy, sc = start
    ex, ey, ec = end
    if not all(math.isfinite(value) for value in (*start, *end)):
        raise ValueError("swept hull poses must be finite")
    distance = math.hypot(ex - sx, ey - sy)
    angular_distance = ((ec - sc + 180.0) % 360.0) - 180.0
    spatial_step = max(min(hull.length_m, hull.beam_m) / METRES_PER_NM / 4.0,
                       1e-5)
    count = max(1, int(math.ceil(distance / spatial_step)),
                int(math.ceil(abs(angular_distance) / 2.0)))
    count = min(count, _MAX_SWEEP_SAMPLES)
    queries = 0
    exact_land = _exact_translational_land_contact(world, start, end, hull)

    def pose(t: float) -> tuple[float, float, float]:
        return (sx + (ex - sx) * t, sy + (ey - sy) * t,
                (sc + angular_distance * t) % 360.0)

    if abs(angular_distance) > _EPSILON_NM:
        exact_land = _conservative_turn_contact(world, start, end, hull, pose)

    previous = 0.0
    for index in range(count + 1):
        current = index / count
        px, py, pc = pose(current)
        contact = grounding_contact(world, px, py, pc, hull)
        queries += 1
        if contact is None:
            if exact_land is not None and exact_land[0] <= current:
                fraction, _, land_contact = exact_land
                safe_fraction = max(0.0, math.nextafter(fraction, 0.0))
                safe_x, safe_y, safe_course = pose(safe_fraction)
                return GroundingSweep(True, safe_x, safe_y, safe_course,
                                      land_contact, fraction, queries)
            previous = current
            continue
        if current == 0.0:
            return GroundingSweep(True, sx, sy, sc, contact, 0.0, queries)
        low, high = previous, current
        for _ in range(_BISECTION_STEPS):
            middle = (low + high) * 0.5
            mx, my, mc = pose(middle)
            queries += 1
            if grounding_contact(world, mx, my, mc, hull) is None:
                low = middle
            else:
                high = middle
        safe_x, safe_y, safe_course = pose(low)
        hit_x, hit_y, hit_course = pose(high)
        contact = grounding_contact(world, hit_x, hit_y, hit_course, hull)
        queries += 1
        if exact_land is not None and exact_land[0] < high:
            fraction, _, contact = exact_land
            safe_fraction = max(0.0, math.nextafter(fraction, 0.0))
            safe_x, safe_y, safe_course = pose(safe_fraction)
            return GroundingSweep(True, safe_x, safe_y, safe_course,
                                  contact, fraction, queries)
        return GroundingSweep(True, safe_x, safe_y, safe_course, contact,
                              high, queries)
    return GroundingSweep(False, ex, ey, ec, None, 1.0, queries)

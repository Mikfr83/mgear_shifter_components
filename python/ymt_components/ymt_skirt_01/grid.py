"""Pure geometry for skirt guide grid locator placement."""

import math


GRID_CLEARANCE = 0.15
GRID_FLARE = 0.3
_NODE_PRIORITY = {"ankle": 0, "knee": 1, "thigh": 2, "calf": 3, "hip": 4}
Vector3 = tuple[float, float, float]
ProfileNode = tuple[float, str, float, float]


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vector3, value: float) -> Vector3:
    return (a[0] * value, a[1] * value, a[2] * value)


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _length(a: Vector3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vector3, threshold: float, label: str) -> Vector3:
    length = _length(a)
    if not math.isfinite(length) or length <= threshold:
        raise ValueError("ymt_skirt_01 cannot compute grid positions: degenerate %s." % label)
    return _scale(a, 1.0 / length)


def _profile_nodes(profile: dict[str, float], knee_t: float) -> list[ProfileNode]:
    nodes = [
        (0.0, "hip", 1.0, 1.0),
        (knee_t * profile["thighPosition"], "thigh", profile["thighRadiusX"], profile["thighRadiusZ"]),
        (knee_t, "knee", profile["kneeRadiusX"], profile["kneeRadiusZ"]),
        (
            knee_t + (1.0 - knee_t) * profile["calfPosition"],
            "calf",
            profile["calfRadiusX"],
            profile["calfRadiusZ"],
        ),
        (1.0, "ankle", profile["ankleRadiusX"], profile["ankleRadiusZ"]),
    ]
    nodes.sort(key=lambda node: (_NODE_PRIORITY[node[1]], node[0]))
    unique = []
    for node in nodes:
        if any(abs(node[0] - existing[0]) <= 1.0e-9 for existing in unique):
            continue
        unique.append(node)
    unique.sort(key=lambda node: node[0])
    return unique


def _profile_radius(
    nodes: list[ProfileNode], station: float, half_hip: float, scale_x: float, scale_z: float
) -> tuple[float, float]:
    if station <= nodes[0][0]:
        x_value, z_value = nodes[0][2], nodes[0][3]
    elif station >= nodes[-1][0]:
        x_value, z_value = nodes[-1][2], nodes[-1][3]
    else:
        for lower, upper in zip(nodes, nodes[1:]):
            if lower[0] <= station <= upper[0]:
                fraction = (station - lower[0]) / (upper[0] - lower[0])
                x_value = lower[2] + (upper[2] - lower[2]) * fraction
                z_value = lower[3] + (upper[3] - lower[3]) * fraction
                break
    return half_hip * scale_x * x_value, half_hip * scale_z * z_value


def _validate_inputs(
    rows: int,
    cols: int,
    references: dict[str, Vector3],
    front: Vector3,
    profile: dict[str, float],
    ring_scale_x: float,
    ring_scale_z: float,
    clearance: float,
    flare: float,
) -> None:
    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 2:
        raise ValueError("rows must be an integer greater than or equal to 2.")
    if not isinstance(cols, int) or isinstance(cols, bool) or cols < 3:
        raise ValueError("cols must be an integer greater than or equal to 3.")
    if not math.isfinite(clearance) or clearance < 0.0 or not math.isfinite(flare) or flare < 0.0:
        raise ValueError("clearance and flare must be finite and non-negative.")
    if not math.isfinite(ring_scale_x) or ring_scale_x <= 0.0 or not math.isfinite(ring_scale_z) or ring_scale_z <= 0.0:
        raise ValueError("ring scales must be finite and positive.")
    if not all(math.isfinite(value) for vector in (*references.values(), front) for value in vector):
        raise ValueError("guide references and front direction must be finite.")
    if not all(math.isfinite(value) for value in profile.values()):
        raise ValueError("leg profile values must be finite.")


def _required_row_radius(
    hip_half: float,
    station: float,
    nodes: list[ProfileNode],
    ring_scale_x: float,
    ring_scale_z: float,
) -> float:
    radius_x, radius_z = _profile_radius(nodes, station, hip_half, ring_scale_x, ring_scale_z)
    return hip_half + max(radius_x, radius_z)


def required_row_radius(
    hip_half: float,
    station: float,
    profile: dict[str, float],
    ring_scale_x: float,
    ring_scale_z: float,
    knee_t: float,
) -> float:
    """Return the enclosing radius required by a row's leg profile section."""
    return _required_row_radius(hip_half, station, _profile_nodes(profile, knee_t), ring_scale_x, ring_scale_z)


def grid_locator_positions(
    rows: int,
    cols: int,
    references: dict[str, Vector3],
    front: Vector3,
    profile: dict[str, float],
    ring_scale_x: float,
    ring_scale_z: float,
    clearance: float = GRID_CLEARANCE,
    flare: float = GRID_FLARE,
) -> list[tuple[int, int, Vector3]]:
    """Return guide locator positions ordered by column, then row."""
    _validate_inputs(rows, cols, references, front, profile, ring_scale_x, ring_scale_z, clearance, flare)

    waist = references["waist"]
    heel_mid = _scale(_add(references["heel_L"], references["heel_R"]), 0.5)
    axis_vector = _sub(heel_mid, waist)
    axis_length = _length(axis_vector)
    epsilon = 1.0e-3 * axis_length
    if not math.isfinite(axis_length) or axis_length <= epsilon:
        raise ValueError("ymt_skirt_01 cannot compute grid positions: degenerate waist-to-heel axis.")
    axis = _unit(axis_vector, epsilon, "waist-to-heel axis")
    front_axis = _sub(front, _scale(axis, _dot(front, axis)))
    # front is a direction of any length; compare it with epsilon at the axis scale.
    front_axis = _unit(_scale(front_axis, axis_length / max(_length(front), 1.0e-12)), epsilon, "projected root front")
    side = _cross(axis, front_axis)

    hip_half = _length(_sub(references["hip_L"], references["hip_R"])) * 0.5
    if not math.isfinite(hip_half) or hip_half <= epsilon:
        raise ValueError("ymt_skirt_01 requires separated hip references to rebuild the grid.")
    hip_mid = _scale(_add(references["hip_L"], references["hip_R"]), 0.5)
    thigh_length = 0.5 * (
        _length(_sub(references["knee_L"], references["hip_L"]))
        + _length(_sub(references["knee_R"], references["hip_R"]))
    )
    calf_length = 0.5 * (
        _length(_sub(references["heel_L"], references["knee_L"]))
        + _length(_sub(references["heel_R"], references["knee_R"]))
    )
    if (
        not math.isfinite(thigh_length)
        or not math.isfinite(calf_length)
        or thigh_length <= epsilon
        or calf_length <= epsilon
    ):
        raise ValueError("ymt_skirt_01 requires non-degenerate thigh and calf references to rebuild the grid.")
    d_hip = _length(_sub(hip_mid, waist))
    d_heel = d_hip + thigh_length + calf_length
    knee_t = thigh_length / (thigh_length + calf_length)
    nodes = _profile_nodes(profile, knee_t)

    output = []
    for col in range(cols):
        angle = 2.0 * math.pi * col / cols
        radial = _add(_scale(front_axis, math.cos(angle)), _scale(side, math.sin(angle)))
        for row in range(rows):
            row_ratio = row / float(rows - 1)
            axial_fraction = 0.15 + 0.75 * row_ratio
            distance = axis_length * axial_fraction
            station = max(0.0, min(1.0, (distance - d_hip) / (d_heel - d_hip)))
            required = _required_row_radius(hip_half, station, nodes, ring_scale_x, ring_scale_z)
            radius = required * (1.0 + clearance) * (1.0 + flare * row_ratio)
            center = _add(waist, _scale(axis, distance))
            output.append((col, row, _add(center, _scale(radial, radius))))
    return output

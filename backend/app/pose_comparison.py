"""Evidence-linked pose overlays; a teaching illustration is never a fault score.

Coordinates are normalized to each *own* frame. Geometry is computed in pixels
so non-square video never distorts lengths/angles. Reference registration uses
one scale and translation per clip, without rotation or mirroring.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from pathlib import Path
from statistics import median

VERSION = "pose-comparison-v1"
TARGET_FILE = Path(__file__).resolve().parents[2] / "references" / "pose-targets.json"
SIDES = {"left": (11, 13, 15), "right": (12, 14, 16)}
CONNECTIONS = [
    [11, 12],
    [11, 13],
    [13, 15],
    [12, 14],
    [14, 16],
    [11, 23],
    [12, 24],
    [23, 24],
    [23, 25],
    [25, 27],
    [24, 26],
    [26, 28],
]
MAX_RELEASE_INTERVAL_US = 150000
MAX_REFERENCE_MATCH_US = 80000


def bilingual(en, zh):
    return {"en": en, "zh": zh}


REASONS = {
    "track_missing": bilingual("Analyze this shot to extract its pose first.", "先分析这球，提取动作轨迹。"),
    "handedness_uncertain": bilingual(
        "Choose your shooting hand in Settings to compare the correct arm.",
        "请在设置中选择出手侧，以便比较正确的手臂。",
    ),
    "release_unknown": bilingual(
        "Mark the release interval to align the guide with your shot.", "请标记离手区间，让示意与这球对齐。"
    ),
    "release_interval_wide": bilingual(
        "Narrow the release interval before comparing the release pose.", "请缩小离手区间后，再比较出手姿态。"
    ),
    "release_context_missing": bilingual(
        "The release neighbourhood has too few clear arm frames for this guide.",
        "离手附近清楚的手臂画面不足，暂时无法生成示意。",
    ),
    "teaching_direction_uncertain": bilingual(
        "The shooting arm is too foreshortened to construct a useful guide from this view.",
        "这个视角下出手臂的投影太短，暂时无法生成有意义的示意。",
    ),
    "teaching_phase_only": bilingual(
        "This arm guide is shown around release and the early finish. Jump to release to compare.",
        "手臂示意用于离手与收势早期；跳到离手位置即可比较。",
    ),
    "arm_not_visible": bilingual(
        "The shooting shoulder, elbow or wrist is hidden in this frame.",
        "这一帧的出手肩、肘或腕没有清楚显示。",
    ),
    "teaching_target_outside_frame": bilingual(
        "The adapted arm guide extends outside this frame.", "按画面臂长生成的示意超出了当前画面。"
    ),
    "select_reference": bilingual(
        "Choose one of your other shots as a reference.", "请选择自己的另一球作为参照。"
    ),
    "self_reference": bilingual("Choose a different shot as the reference.", "请选择另一球作为参照。"),
    "reference_unanalyzed": bilingual("Analyze the reference shot first.", "请先分析参照球。"),
    "reference_handedness_uncertain": bilingual(
        "Choose the reference shot's shooting hand before overlaying it.", "叠加前请先确定参照球的出手侧。"
    ),
    "handedness_mismatch": bilingual(
        "The shooting hands differ; a mirrored pose would not be a reliable comparison.",
        "两球出手侧不同，镜像叠加不能提供可靠比较。",
    ),
    "context_mismatch": bilingual(
        "Use shots with the same shot type and camera view.", "请选用投篮类型和拍摄视角相同的两球。"
    ),
    "view_unverified": bilingual(
        "Confirm a matching fixed camera view in Settings before overlaying the shots.",
        "叠加前，请在设置中确认两球使用相同固定机位。",
    ),
    "reference_release_unknown": bilingual(
        "Mark the reference shot's release interval to align the two shots.",
        "请标记参照球的离手区间，让两球对齐。",
    ),
    "reference_release_interval_wide": bilingual(
        "Narrow the reference shot's release interval before overlaying it.", "叠加前请缩小参照球的离手区间。"
    ),
    "alignment_not_visible": bilingual(
        "Clear hips and torso near release are needed to align the two shots.",
        "需要两球离手附近清楚的髋部和躯干，才能对齐。",
    ),
    "reference_context_missing": bilingual(
        "The reference has no matching frame at this time relative to release.",
        "参照球在这个相对离手时刻没有对应画面。",
    ),
    "reference_pose_not_visible": bilingual(
        "The reference pose is not clear enough in the matching frame.", "参照球的对应帧没有足够清楚的姿态。"
    ),
    "own_pose_not_visible": bilingual(
        "Your body pose is not clear enough in this frame.", "这一帧没有足够清楚的身体姿态。"
    ),
}


def _visible(point):
    return bool(
        point
        and all(isinstance(point.get(k), (int, float)) and math.isfinite(point[k]) for k in ("x", "y"))
        and point.get("visibility", 0) >= 0.5
        and 0 <= point["x"] <= 1
        and 0 <= point["y"] <= 1
    )


def _point(frame, index):
    points = frame.get("landmarks") or []
    point = points[index] if index < len(points) else None
    return point if _visible(point) else None


def _pixel(frame, point):
    return point["x"] * frame["width"], point["y"] * frame["height"]


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _arm(frame, side):
    points = [_point(frame, i) for i in SIDES[side]]
    if not all(points):
        return None
    return [_pixel(frame, point) for point in points]


def _angle(points):
    a, b, c = points
    u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    length = math.hypot(*u) * math.hypot(*v)
    if length < 1e-8:
        return None
    return math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / length))))


def _torso(frame):
    lengths = []
    for shoulder, hip in ((11, 23), (12, 24)):
        a, b = _point(frame, shoulder), _point(frame, hip)
        if a and b:
            lengths.append(_distance(_pixel(frame, a), _pixel(frame, b)))
    return sum(lengths) / len(lengths) if lengths and min(lengths) > 10 else None


def _hips(frame):
    points = [_point(frame, i) for i in (23, 24)]
    if not all(points):
        return None
    pixels = [_pixel(frame, p) for p in points]
    return tuple(sum(p[i] for p in pixels) / 2 for i in (0, 1))


def _side(asset):
    # Explicit input resolves an old ambiguous estimate without trusting it.
    requested = (asset.get("analysis_config") or {}).get("handedness")
    if requested in SIDES:
        return requested
    measured = asset.get("measurements") or {}
    if measured.get("side_source") == "ambiguous_estimate":
        return None
    return measured.get("side") if measured.get("side") in SIDES else None


def _release(asset):
    release = (asset.get("phases") or {}).get("release") or {}
    span = release.get("range_us")
    if not span or len(span) != 2 or not all(isinstance(v, (int, float)) for v in span) or span[1] < span[0]:
        return None, "release_unknown"
    if span[1] - span[0] > MAX_RELEASE_INTERVAL_US:
        return None, "release_interval_wide"
    return sum(span) / 2, None


def _evidence(asset, frame):
    return {
        "asset_id": asset["id"],
        "frame_id": frame["frame_id"],
        "time_us": frame["time_us"],
        "source_time_us": frame["source_time_us"],
    }


def _phase(asset, frame, anchor):
    if anchor is None:
        return "unknown"
    lo, hi = asset["phases"]["release"]["range_us"]
    time = frame["time_us"]
    if time < lo:
        return "pre_release"
    if time <= hi:
        return "release"
    return "follow_through" if time <= anchor + 800000 else "after_follow_through"


def _unavailable(frame, reason):
    frame.update(available=False, reason=reason, reason_text=REASONS[reason])
    return frame


def _base_frame(asset, frame, anchor):
    return {
        "frame_index": frame["frame_index"],
        "phase": _phase(asset, frame, anchor),
        "available": False,
        "target_landmarks": [None] * 33,
        "connections": [],
        "own_evidence": _evidence(asset, frame),
        "deltas": [],
    }


def _finish(result):
    available = [f for f in result["frames"] if f["available"]]
    result["available_frames"] = len(available)
    result["total_frames"] = len(result["frames"])
    result["available_frame_range"] = (
        [available[0]["frame_index"], available[-1]["frame_index"]] if available else None
    )
    if available:
        result["comparison_status"] = (
            "teaching_illustration" if result["mode"] == "teaching" else "conditional_personal_reference"
        )
        anchor = result["release_anchor_us"]
        result["recommended_frame_index"] = min(
            available, key=lambda f: abs(f["own_evidence"]["time_us"] - anchor)
        )["frame_index"]
    else:
        result["comparison_status"] = "unavailable"
        result["recommended_frame_index"] = None
        if not result.get("reason"):
            relevant = [f for f in result["frames"] if f.get("reason") != "teaching_phase_only"]
            reason = relevant[0]["reason"] if relevant else "track_missing"
            result.update(reason=reason, reason_text=REASONS[reason])
    return result


def _block(result, asset, frames, anchor, reason):
    result.update(reason=reason, reason_text=REASONS[reason])
    result["frames"] = [_unavailable(_base_frame(asset, f, anchor), reason) for f in frames]
    return _finish(result)


def _delta(key, label, value, unit, own, target, target_is_illustration):
    return {
        "key": key,
        "label": label,
        "value": round(value, 3),
        "unit": unit,
        "own_value": round(own, 3),
        "target_value": round(target, 3),
        "interpretation": "descriptive_difference_not_fault_score",
        "target_is_illustration": target_is_illustration,
    }


def _deltas(frame, target_points, side, teaching):
    own = _arm(frame, side)
    target_frame = {**frame, "landmarks": target_points}
    target = _arm(target_frame, side)
    if not own or not target:
        return []
    output = []
    own_angle, target_angle = _angle(own), _angle(target)
    if own_angle is not None and target_angle is not None:
        output.append(
            _delta(
                "projected_elbow_angle_difference",
                bilingual("Projected elbow angle difference", "投影肘角差"),
                own_angle - target_angle,
                "degrees_projection",
                own_angle,
                target_angle,
                teaching,
            )
        )
    torso = _torso(frame)
    if torso:
        own_height = (own[0][1] - own[2][1]) / torso
        target_height = (own[0][1] - target[2][1]) / torso
        output.append(
            _delta(
                "wrist_height_difference",
                bilingual("Hand height difference", "手位高度差"),
                own_height - target_height,
                "torso_lengths",
                own_height,
                target_height,
                teaching,
            )
        )
    return output


def _teaching_geometry(asset, frames, side, anchor, spec):
    near = [f for f in frames if abs(f["time_us"] - anchor) <= 100000]
    samples = []
    for frame in near:
        arm, torso = _arm(frame, side), _torso(frame)
        if not arm or not torso:
            continue
        a, b, c = arm
        upper, lower = _distance(a, b), _distance(b, c)
        reach = _distance(a, c)
        if min(upper, lower) < max(5, torso * 0.08) or reach < torso * 0.15:
            continue
        samples.append((frame, arm, upper, lower, ((c[0] - a[0]) / reach, (c[1] - a[1]) / reach)))
    if len(samples) < 3:
        return None, "release_context_missing"
    upper, lower = (median(s[i] for s in samples) for i in (2, 3))
    direction = tuple(median(s[4][i] for s in samples) for i in (0, 1))
    magnitude = math.hypot(*direction)
    if magnitude < 0.65 or not math.isfinite(magnitude):
        return None, "teaching_direction_uncertain"
    direction = tuple(v / magnitude for v in direction)
    # The illustrative opening is disclosed, never used as a pass/fail threshold.
    # Do not tell an already more extended arm to bend toward the template.
    observed_angle = median(_angle(s[1]) for s in samples)
    target_angle = max(spec["template_angle_deg"], min(179, observed_angle))
    reach = math.sqrt(
        upper * upper + lower * lower - 2 * upper * lower * math.cos(math.radians(target_angle))
    )
    along = (upper * upper + reach * reach - lower * lower) / (2 * reach)
    perpendicular = math.sqrt(max(0, upper * upper - along * along))
    # Retain the observed elbow side of the shoulder-to-wrist axis.
    bends = [(s[1][1][0] - s[1][0][0]) * -s[4][1] + (s[1][1][1] - s[1][0][1]) * s[4][0] for s in samples]
    bend = 1 if median(bends) >= 0 else -1
    dx, dy = direction
    elbow = (along * dx - bend * perpendicular * dy, along * dy + bend * perpendicular * dx)
    wrist = (reach * dx, reach * dy)
    return {
        "elbow_offset_px": elbow,
        "wrist_offset_px": wrist,
        "upper_arm_px": upper,
        "forearm_px": lower,
        "direction": direction,
        "adapted_angle_deg": target_angle,
        "observed_release_angle_deg": observed_angle,
        "evidence": [_evidence(asset, s[0]) for s in samples],
    }, None


def _teaching(result, asset, frames, side, anchor, spec):
    geometry, reason = _teaching_geometry(asset, frames, side, anchor, spec)
    if reason:
        return _block(result, asset, frames, anchor, reason)
    result["adaptation"] = geometry
    shoulder_index, elbow_index, wrist_index = SIDES[side]
    lower = asset["phases"]["release"]["range_us"][0]
    for own in frames:
        frame = _base_frame(asset, own, anchor)
        result["frames"].append(frame)
        if not lower <= own["time_us"] <= anchor + spec["display_after_release_us"]:
            _unavailable(frame, "teaching_phase_only")
            continue
        arm = _arm(own, side)
        if not arm:
            _unavailable(frame, "arm_not_visible")
            continue
        sx, sy = arm[0]
        points = [None] * 33
        for index, (dx, dy) in (
            (shoulder_index, (0, 0)),
            (elbow_index, geometry["elbow_offset_px"]),
            (wrist_index, geometry["wrist_offset_px"]),
        ):
            points[index] = {
                "x": (sx + dx) / own["width"],
                "y": (sy + dy) / own["height"],
                "visibility": 1,
                "synthetic": True,
            }
        if not all(_visible(points[i]) for i in SIDES[side]):
            _unavailable(frame, "teaching_target_outside_frame")
            continue
        frame.update(
            available=True,
            target_landmarks=points,
            connections=[[shoulder_index, elbow_index], [elbow_index, wrist_index]],
            deltas=_deltas(own, points, side, True),
            transformation={"kind": "own_shoulder_anchor", "rotation_degrees": 0},
        )
    return _finish(result)


def _registration(frames, anchor):
    # Robust single clip scale; do not continuously rescale away pose differences.
    lengths = [length for frame in frames if (length := _torso(frame)) is not None]
    near = [f for f in frames if abs(f["time_us"] - anchor) <= 80000 and _hips(f)]
    if len(lengths) < 3 or not near:
        return None
    chosen = min(near, key=lambda f: abs(f["time_us"] - anchor))
    return {"torso_px": median(lengths), "hip_anchor_px": _hips(chosen), "frame": chosen}


def _nearest(frames, times, timestamp):
    # Never clamp a shortened reference to its first/last pose.
    if not times or timestamp < times[0] or timestamp > times[-1]:
        return None
    at = bisect_left(times, timestamp)
    choices = frames[max(0, at - 1) : min(len(frames), at + 1)]
    match = min(choices, key=lambda f: abs(f["time_us"] - timestamp))
    return match if abs(match["time_us"] - timestamp) <= MAX_REFERENCE_MATCH_US else None


def _reference(result, asset, frames, side, anchor, reference, reference_track, assume_same_view):
    if not reference:
        return _block(result, asset, frames, anchor, "select_reference")
    if reference["id"] == asset["id"]:
        return _block(result, asset, frames, anchor, "self_reference")
    refs = (reference_track or {}).get("frames") or []
    if not refs:
        return _block(result, asset, frames, anchor, "reference_unanalyzed")
    ref_side = _side(reference)
    if not ref_side:
        return _block(result, asset, frames, anchor, "reference_handedness_uncertain")
    if side != ref_side:
        return _block(result, asset, frames, anchor, "handedness_mismatch")
    config, ref_config = asset.get("analysis_config") or {}, reference.get("analysis_config") or {}
    if any(
        config.get(key) in (None, "unknown") or config[key] != ref_config.get(key)
        for key in ("shot_type", "camera_view")
    ):
        return _block(result, asset, frames, anchor, "context_mismatch")
    own_group, ref_group = (
        (asset.get("upstream") or {}).get("camera_group"),
        (reference.get("upstream") or {}).get("camera_group"),
    )
    if not (own_group and own_group == ref_group) and not assume_same_view:
        return _block(result, asset, frames, anchor, "view_unverified")
    ref_anchor, reason = _release(reference)
    if reason:
        return _block(result, asset, frames, anchor, "reference_" + reason)
    own_registration, ref_registration = _registration(frames, anchor), _registration(refs, ref_anchor)
    if not own_registration or not ref_registration:
        return _block(result, asset, frames, anchor, "alignment_not_visible")
    scale = own_registration["torso_px"] / ref_registration["torso_px"]
    ox, oy = own_registration["hip_anchor_px"]
    rx, ry = ref_registration["hip_anchor_px"]
    transform = {
        "kind": "fixed_release_hip_translation_and_uniform_torso_scale",
        "scale": scale,
        "translation_px": [ox - scale * rx, oy - scale * ry],
        "rotation_degrees": 0,
        "mirrored": False,
        "own_anchor_evidence": _evidence(asset, own_registration["frame"]),
        "reference_anchor_evidence": _evidence(reference, ref_registration["frame"]),
        "camera_basis": "matching_camera_group"
        if own_group and own_group == ref_group
        else "user_confirmed_same_view",
    }
    result.update(
        transformation=transform,
        reference_release_anchor_us=ref_anchor,
        reference_id=reference["id"],
        reference_revision=reference.get("revision"),
    )
    refs = sorted(refs, key=lambda f: f["time_us"])
    times = [f["time_us"] for f in refs]
    for own in frames:
        frame = _base_frame(asset, own, anchor)
        result["frames"].append(frame)
        timestamp = ref_anchor + own["time_us"] - anchor
        match = _nearest(refs, times, timestamp)
        if not match:
            _unavailable(frame, "reference_context_missing")
            continue
        frame["reference_evidence"] = _evidence(reference, match)
        frame["alignment_error_us"] = match["time_us"] - timestamp
        if not _hips(own) or not _torso(own):
            _unavailable(frame, "own_pose_not_visible")
            continue
        if not _hips(match) or not _torso(match):
            _unavailable(frame, "reference_pose_not_visible")
            continue
        points = [None] * 33
        for i in range(33):
            point = _point(match, i)
            if point:
                x, y = _pixel(match, point)
                points[i] = {
                    "x": (scale * (x - rx) + ox) / own["width"],
                    "y": (scale * (y - ry) + oy) / own["height"],
                    "visibility": point["visibility"],
                }
        connections = [
            [a, b] for a, b in CONNECTIONS if points[a] and points[b] and _point(own, a) and _point(own, b)
        ]
        if not connections:
            _unavailable(frame, "reference_pose_not_visible")
            continue
        frame.update(
            available=True,
            target_landmarks=points,
            connections=connections,
            deltas=_deltas(own, points, side, False),
        )
    return _finish(result)


def build_pose_comparison(
    asset, track, reference=None, reference_track=None, mode="teaching", assume_same_view=False
):
    """Build an arm teaching guide or an actual personal-reference pose overlay.

    Callers retain both asset revisions with their result. Rebuild after phase,
    handedness or reference changes; no video or pose data leaves this process.
    """
    if mode not in ("teaching", "reference"):
        raise ValueError("Unknown pose comparison mode")
    spec = json.loads(TARGET_FILE.read_text())
    frames = (track or {}).get("frames") or []
    anchor, release_reason = _release(asset)
    result = {
        "version": VERSION,
        "mode": mode,
        "coordinate_system": "normalized_own_frame",
        "asset_id": asset["id"],
        "asset_revision": asset.get("revision"),
        "label": spec["label"] if mode == "teaching" else bilingual("Your reference shot", "自己的参照球"),
        "description": spec["description"]
        if mode == "teaching"
        else bilingual(
            "The selected shot is aligned by release time and a fixed hip translation and torso scale. No rotation or mirroring is applied; differences are descriptive, not faults.",
            "按离手时刻对齐两球，再按离手髋部位置与躯干大小平移、等比缩放。不会旋转或镜像；差异用于观察，不代表错误。",
        ),
        "source_type": spec["source_type"] if mode == "teaching" else "personal_reference_video",
        "source_ids": spec["source_ids"] if mode == "teaching" else [],
        "comparison_status": "unavailable",
        "release_anchor_us": anchor,
        "measured_expert_motion": False,
        "grading_thresholds": None,
        "frames": [],
    }
    if mode == "teaching":
        result.update(
            target_version=spec["version"],
            teach_target_basis=spec["teach_target_basis"],
            template_angle_deg=spec["template_angle_deg"],
            rubric_ids=spec["rubric_ids"],
            display_window_policy=spec["display_window_policy"],
            scope="shooting_arm_only",
        )
    if not frames:
        return _block(result, asset, frames, anchor, "track_missing")
    side = _side(asset)
    result["side"] = side
    if not side:
        return _block(result, asset, frames, anchor, "handedness_uncertain")
    if release_reason:
        return _block(result, asset, frames, anchor, release_reason)
    if mode == "teaching":
        return _teaching(result, asset, frames, side, anchor, spec)
    return _reference(result, asset, frames, side, anchor, reference, reference_track, assume_same_view)

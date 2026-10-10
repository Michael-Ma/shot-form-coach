from __future__ import annotations

import math
from statistics import median

from .perception import angle, joint, visible


def pixels(frame, point):
    return point["x"] * frame["width"], point["y"] * frame["height"]


def torso_length(frame):
    lengths = []
    for side in ["left", "right"]:
        a, b = joint(frame, side + "_shoulder"), joint(frame, side + "_hip")
        if visible(a) and visible(b):
            ax, ay = pixels(frame, a)
            bx, by = pixels(frame, b)
            lengths.append(math.hypot(ax - bx, ay - by))
    return sum(lengths) / len(lengths) if lengths and min(lengths) > 10 else None


def wrist_height(frame, side):
    wrist, shoulder = joint(frame, side + "_wrist"), joint(frame, side + "_shoulder")
    length = torso_length(frame)
    if not length or not visible(wrist) or not visible(shoulder):
        return None
    return (shoulder["y"] - wrist["y"]) * frame["height"] / length


def wrist_above_face(frame, side):
    """Image-space wrist height relative to the nose, not a 3-D release height."""
    wrist, face = joint(frame, side + "_wrist"), joint(frame, "nose")
    length = torso_length(frame)
    if not length or not visible(wrist) or not visible(face):
        return None
    return (face["y"] - wrist["y"]) * frame["height"] / length


def aggregate_window(window, metric):
    valid = [(f, metric(f)) for f in window]
    valid = [(f, v) for f, v in valid if v is not None and math.isfinite(v)]
    if len(valid) < 3 or len(valid) < 0.7 * len(window):
        return None, []
    return sum(v for _, v in valid) / len(valid), [f for f, _ in valid]


def human_motion_measures(frames, phases, side, side_source):
    """Additional descriptive metrics. Constants are measurement gates, not form standards."""
    release = (phases or {}).get("release")
    anchor = release_anchor(phases)
    keys = [
        ("release_wrist_height", "torso_lengths"),
        ("release_wrist_above_face", "torso_lengths"),
        ("release_elbow_angle", "degrees_projection"),
        ("finish_above_shoulder_ms", "milliseconds"),
    ]
    reason = "release_unknown" if anchor is None else None
    if side_source == "ambiguous_estimate":
        reason = "handedness_uncertain"
    if release and release["range_us"][1] - release["range_us"][0] > 150000:
        reason = "release_interval_wide"
    if reason:
        return [measurement(key, None, unit, [], reason) for key, unit in keys]

    near = frame_window(frames, release["range_us"][0] - 50000, release["range_us"][1] + 50000)
    output = []
    for key, unit, metric in [
        ("release_wrist_height", "torso_lengths", lambda f: wrist_height(f, side)),
        ("release_wrist_above_face", "torso_lengths", lambda f: wrist_above_face(f, side)),
        ("release_elbow_angle", "degrees_projection", lambda f: angle(f, side)),
    ]:
        value, evidence = aggregate_window(near, metric)
        output.append(measurement(key, value, unit, evidence, "track_gaps" if value is None else None))

    # A missing frame or gap can hide when the hand falls. Do not count across it.
    # Use the latest possible release for conservative "at least" durations.
    finish_start = release["range_us"][1]
    post = frame_window(frames, finish_start, finish_start + 1000000)
    continuous, previous = [], finish_start
    for frame in post:
        height = wrist_height(frame, side)
        if height is None or frame["time_us"] - previous > 120000:
            break
        continuous.append((frame, height))
        previous = frame["time_us"]
    enough = len(continuous) >= 5 and continuous[-1][0]["time_us"] - finish_start >= 300000
    initial = continuous[:3]
    raised = initial and len(initial) == 3 and all(h > 0.05 for _, h in initial)
    if not enough or not raised:
        output.append(
            measurement(
                "finish_above_shoulder_ms",
                None,
                "milliseconds",
                [],
                "track_gaps" if not enough else "raised_finish_not_observed",
            )
        )
        return output
    crossing, confirmed_at, lowered_run = None, None, []
    for frame, height in continuous:
        lowered_run = lowered_run + [frame] if height < -0.05 else []
        if len(lowered_run) >= 3 and frame["time_us"] - lowered_run[0]["time_us"] >= 60000:
            crossing, confirmed_at = lowered_run[0], frame
            break
    if crossing:
        end = crossing
        evidence = [f for f, _ in continuous if f["time_us"] <= confirmed_at["time_us"]]
    else:
        # Absence of a sustained lowering is not proof of being continuously
        # above the shoulder. Stop the lower bound at the first ambiguous point.
        prefix = []
        for frame, height in continuous:
            if height <= 0.05:
                break
            prefix.append(frame)
        if not prefix or prefix[-1]["time_us"] - finish_start < 300000:
            output.append(
                measurement("finish_above_shoulder_ms", None, "milliseconds", [], "finish_position_uncertain")
            )
            return output
        end, evidence = prefix[-1], prefix
    held = measurement(
        "finish_above_shoulder_ms", (end["time_us"] - finish_start) / 1000, "milliseconds", evidence
    )
    held.update(
        lower_bound=crossing is None,
        crossed_shoulder=crossing is not None,
        observed_to_ms=(continuous[-1][0]["time_us"] - finish_start) / 1000,
    )
    output.append(held)
    return output


def choose_side(frames, requested="auto"):
    if requested != "auto":
        return requested, "user_setting"
    scores = {}
    for side in ["left", "right"]:
        values = [angle(f, side) for f in frames[len(frames) // 2 :]]
        values = [v for v in values if v is not None]
        scores[side] = median(values) if values else 0
    chosen = max(scores, key=scores.get)
    return chosen, "estimated_arm_extension" if abs(
        scores["left"] - scores["right"]
    ) > 10 else "ambiguous_estimate"


def recent_loading_bottom(track, anchor_us):
    """Find the final load near this release; earlier retrieval/setup is not shooting rhythm."""
    if anchor_us is None:
        return None
    window = []
    for i, frame in enumerate(track["frames"]):
        if not anchor_us - 1_250_000 <= frame["time_us"] < anchor_us:
            continue
        hips = [joint(frame, side + "_hip") for side in ("left", "right")]
        if all(visible(p) for p in hips):
            window.append((i, frame, sum(p["y"] for p in hips) / 2))
    if len(window) < 5:
        return None
    smoothed = []
    for n, (i, frame, value) in enumerate(window):
        neighbours = [
            v for _, f, v in window[max(0, n - 1) : n + 2] if abs(f["time_us"] - frame["time_us"]) <= 100_000
        ]
        smoothed.append((i, frame, median(neighbours)))
    bottom = max(smoothed, key=lambda item: item[2])
    later = [v for _, frame, v in smoothed if frame["time_us"] > bottom[1]["time_us"]]
    # A maximum at the observed boundary or no observable rise is incomplete evidence.
    if bottom[0] == window[0][0] or len(later) < 2 or bottom[2] - min(later) < 0.005:
        return None
    return {
        "range_us": [bottom[1]["time_us"]] * 2,
        "frame_range": [bottom[0]] * 2,
        "source": "pose_candidate",
        "quality": "recent_pre_release_extremum",
        "derivation_version": "recent-load-v2",
    }


def current_phases(track, phases):
    result = dict(phases or {})
    loading = result.get("loading_bottom")
    if not loading or loading.get("source") == "pose_candidate":
        anchor = release_anchor(result)
        if anchor is None:
            peak = result.get("extension_peak")
            anchor = peak["range_us"][0] if peak else None
        result["loading_bottom"] = recent_loading_bottom(track, anchor)
    return result


def propose_phases(track, config):
    frames = track["frames"]
    side, side_source = choose_side(frames, config.get("handedness", "auto"))
    valid_heights = [(i, wrist_height(f, side)) for i, f in enumerate(frames)]
    valid_heights = [(i, h) for i, h in valid_heights if h is not None]
    if not valid_heights:
        return {"release": None}, side, side_source
    peak = max(valid_heights, key=lambda p: p[1])[0]
    phases = {
        "extension_peak": {
            "range_us": [frames[peak]["time_us"]] * 2,
            "frame_range": [peak, peak],
            "source": "pose_candidate",
            "quality": "projected_extremum",
        },
        "release": None,
    }
    contact, candidates = None, []
    for i, frame in enumerate(frames):
        ball = frame.get("ball")
        if not ball or ball["score"] < 0.2:
            continue
        hand = [joint(frame, side + "_wrist"), joint(frame, side + "_index")]
        hand = [p for p in hand if visible(p)]
        if not hand:
            continue
        distance = min(
            math.hypot((ball["x"] - p["x"]) * frame["width"], (ball["y"] - p["y"]) * frame["height"])
            for p in hand
        )
        radius = ball["radius_px"]
        if distance <= radius * 1.8 + 9:
            contact = i
        elif distance >= radius * 2.4 + 15 and contact is not None and i - contact <= 6:
            if abs(frames[i]["time_us"] - frames[peak]["time_us"]) <= 650000:
                candidates.append((contact, i))
    if candidates:
        a, b = min(candidates, key=lambda pair: abs(frames[pair[1]]["time_us"] - frames[peak]["time_us"]))
        phases["release"] = {
            "range_us": [frames[a]["time_us"], frames[b]["time_us"]],
            "frame_range": [a, b],
            "source": "ball_hand_separation_candidate",
            "quality": "needs_review",
        }
    phases = current_phases(track, phases)
    return phases, side, side_source


def release_anchor(phases):
    release = (phases or {}).get("release")
    return sum(release["range_us"]) / 2 if release else None


def frame_window(frames, start, end):
    return [f for f in frames if start <= f["time_us"] <= end]


def measurement(key, value, unit, evidence, reason=None):
    return {
        "id": key,
        "key": key,
        "value": value,
        "unit": unit,
        "status": "available" if value is not None else "unavailable",
        "reason": reason,
        "coordinate_system": "image_projection",
        "evidence_frame_ids": [f["frame_id"] for f in evidence],
        "source_range_us": [evidence[0]["source_time_us"], evidence[-1]["source_time_us"]]
        if evidence
        else None,
    }


def measure(track, phases, side, side_source):
    frames = track["frames"]
    anchor = release_anchor(phases)
    curve = [
        {
            "time_us": f["time_us"],
            "source_time_us": f["source_time_us"],
            "frame_id": f["frame_id"],
            "wrist_height": wrist_height(f, side),
            "elbow_angle": angle(f, side),
        }
        for f in frames
    ]
    flags = []
    if anchor is None:
        flags.append("release_unknown")
    if side_source == "ambiguous_estimate":
        flags.append("handedness_uncertain")
    valid = sum(c["wrist_height"] is not None for c in curve)
    if valid < 0.7 * len(frames):
        flags.append("track_gaps")
    if sum(f.get("ball") is not None for f in frames) < 3:
        flags.append("ball_not_visible")
    measurements = []
    if anchor is None:
        for key, unit in [
            ("wrist_height_early", "torso_lengths"),
            ("wrist_height_late", "torso_lengths"),
            ("arm_lowering", "torso_lengths"),
            ("elbow_extension_change", "degrees_projection"),
            ("loading_to_release", "milliseconds"),
        ]:
            measurements.append(measurement(key, None, unit, [], "release_unknown"))
    else:
        early, late = (
            frame_window(frames, anchor + 100000, anchor + 300000),
            frame_window(frames, anchor + 600000, anchor + 800000),
        )

        def aggregate(window, metric):
            return aggregate_window(window, metric)[0]

        e, late_height = (
            aggregate(early, lambda f: wrist_height(f, side)),
            aggregate(late, lambda f: wrist_height(f, side)),
        )
        enough_context = frames[-1]["time_us"] >= anchor + 700000
        if not enough_context:
            flags.append("post_context_short")
            late_height = None
        measurements += [
            measurement("wrist_height_early", e, "torso_lengths", early, "track_gaps" if e is None else None),
            measurement(
                "wrist_height_late",
                late_height,
                "torso_lengths",
                late,
                "post_context_short" if not enough_context else "track_gaps" if late_height is None else None,
            ),
        ]
        lowering = e - late_height if e is not None and late_height is not None else None
        measurements.append(
            measurement(
                "arm_lowering",
                lowering,
                "torso_lengths",
                early + late,
                "post_context_short" if not enough_context else "track_gaps" if lowering is None else None,
            )
        )
        ea, la = aggregate(early, lambda f: angle(f, side)), aggregate(late, lambda f: angle(f, side))
        change = la - ea if ea is not None and la is not None and enough_context else None
        measurements.append(
            measurement(
                "elbow_extension_change",
                change,
                "degrees_projection",
                early + late,
                "post_context_short" if not enough_context else "track_gaps" if change is None else None,
            )
        )
        loading = (phases or {}).get("loading_bottom")
        duration = (anchor - sum(loading["range_us"]) / 2) / 1000 if loading else None
        if duration is not None and duration < 0:
            duration = None
        evidence = (
            frame_window(frames, sum(loading["range_us"]) / 2, anchor)
            if loading and duration is not None
            else []
        )
        measurements.append(
            measurement(
                "loading_to_release",
                duration,
                "milliseconds",
                evidence,
                "loading_unknown" if duration is None else None,
            )
        )
    measurements.extend(human_motion_measures(frames, phases, side, side_source))
    return {
        "version": "projection-measures-v2",
        "side": side,
        "side_source": side_source,
        "measurements": measurements,
        "curve": curve,
        "flags": sorted(set(flags)),
        "visible_frames": valid,
        "total_frames": len(frames),
        "release_anchor_us": anchor,
        "phase_source": (phases.get("release") or {}).get("source"),
    }


def compare(asset, own, reference=None, ref_measures=None, assume_same_view=False):
    if not reference:
        return {"status": "no_reference", "differences": [], "reason": "select_reference"}
    if (
        own.get("side_source") == "ambiguous_estimate"
        or (ref_measures or {}).get("side_source") == "ambiguous_estimate"
    ):
        return {"status": "qualitative_only", "differences": [], "reason": "handedness_uncertain"}
    if own.get("side") != (ref_measures or {}).get("side"):
        return {"status": "qualitative_only", "differences": [], "reason": "handedness_mismatch"}
    a, b = asset.get("analysis_config", {}), reference.get("analysis_config", {})
    same_group = bool(asset.get("upstream", {}).get("camera_group")) and asset["upstream"][
        "camera_group"
    ] == reference.get("upstream", {}).get("camera_group")
    if (
        a.get("shot_type") in (None, "unknown")
        or a.get("camera_view") in (None, "unknown")
        or a.get("shot_type") != b.get("shot_type")
        or a.get("camera_view") != b.get("camera_view")
    ):
        return {"status": "qualitative_only", "differences": [], "reason": "context_mismatch"}
    if not same_group and not assume_same_view:
        return {"status": "qualitative_only", "differences": [], "reason": "view_unverified"}
    if not ref_measures:
        return {"status": "qualitative_only", "differences": [], "reason": "reference_unanalyzed"}
    values = {m["key"]: m for m in ref_measures["measurements"]}
    differences = []
    for metric in own["measurements"]:
        other = values.get(metric["key"])
        if (
            metric["value"] is not None
            and other
            and other["value"] is not None
            and not metric.get("lower_bound")
            and not other.get("lower_bound")
        ):
            differences.append(
                {
                    "measurement_id": metric["id"],
                    "key": metric["key"],
                    "value": metric["value"],
                    "reference_value": other["value"],
                    "difference": metric["value"] - other["value"],
                    "unit": metric["unit"],
                }
            )
    return {
        "status": "conditional_projection_comparison",
        "differences": differences,
        "reason": "same_view_assumed",
        "reference_id": reference["id"],
        "reference_revision": reference["revision"],
    }


def findings(measures, comparison):
    metrics = {m["key"]: m for m in measures["measurements"]}
    result = []
    lowering = metrics["arm_lowering"]
    if lowering["value"] is not None:
        diff = next((d for d in comparison["differences"] if d["key"] == "arm_lowering"), None)
        result.append(
            {
                "id": "follow_through_observation",
                "attribute": "follow_through",
                "kind": "observed_difference" if diff else "observed_change",
                "measurement_refs": ["arm_lowering", "wrist_height_early", "wrist_height_late"],
                "evidence_frame_ids": lowering["evidence_frame_ids"],
                "source_ids": ["curry-mechanics", "curry-form-practice", "attention-imagery-2021"],
                "comparison": diff,
                "cue_id": "repeatable_finish",
                "coaching_status": "hypothesis_to_test",
                "cause_of_miss": None,
            }
        )
    rhythm = metrics["loading_to_release"]
    if rhythm["value"] is not None:
        result.append(
            {
                "id": "rhythm_observation",
                "attribute": "rhythm",
                "kind": "observed_timing",
                "measurement_refs": ["loading_to_release"],
                "evidence_frame_ids": rhythm["evidence_frame_ids"],
                "source_ids": ["curry-mechanics"],
                "cue_id": "coordinated_rise",
                "coaching_status": "hypothesis_to_test",
                "cause_of_miss": None,
            }
        )
    return result[:3]

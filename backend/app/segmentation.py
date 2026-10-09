"""Local, identity-gated wrist-rise proposals. These are never verified shot counts."""

from __future__ import annotations

import math
from collections import Counter
from fractions import Fraction

import av
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .db import ident

METHOD = "local_pose_wrist_rise_v2"
SAMPLE_INTERVAL_US = 200_000
MAX_GAP_US = 600_000
MAX_RISE_US = 2_500_000
TRACE_LIMIT = 1200
ANOMALY_LIMIT = 400
TORSO = (11, 12, 23, 24)
UPPER_SUPPORT = (0, 13, 14, 15, 16)
LOWER_SUPPORT = (25, 26, 27, 28)
SUPPORT = UPPER_SUPPORT + LOWER_SUPPORT
DUPLICATE_THRESHOLDS = {
    "scale_ratio_max": 1.25,
    "center_distance_max": 0.12,
    "torso_mean_distance_max": 0.16,
    "torso_max_distance_max": 0.28,
    "support_median_distance_max": 0.20,
    "support_close_distance_max": 0.32,
    "support_close_fraction_min": 0.75,
    "shared_support_min": 4,
}
TRACK_THRESHOLDS = {
    "scale_ratio_max": 1.4,
    "center_distance_max": 0.9,
    "torso_mean_distance_max": 1.0,
    "centered_torso_distance_max": 0.28,
}
REACQUIRE_THRESHOLDS = {
    **TRACK_THRESHOLDS,
    "center_distance_max": 0.55,
    "torso_mean_distance_max": 0.60,
}


def _value(point, name):
    return point.get(name) if isinstance(point, dict) else getattr(point, name, None)


def _reliable(point):
    if point is None:
        return False
    values = [_value(point, k) for k in ("x", "y", "visibility", "presence")]
    return (
        all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
        and 0 <= values[0] <= 1
        and 0 <= values[1] <= 1
        and min(values[2:]) >= 0.6
    )


def _finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def pose_geometry(points, width, height):
    """Compact geometry in image-height units; x distances account for aspect ratio."""
    if len(points) < 29 or not all(_reliable(points[i]) for i in TORSO):
        return None
    aspect = width / height
    coords = {
        i: (float(_value(points[i], "x")) * aspect, float(_value(points[i], "y")))
        for i in TORSO + SUPPORT
        if _reliable(points[i])
    }
    scale = (math.dist(coords[11], coords[23]) + math.dist(coords[12], coords[24])) / 2
    if scale < 0.04:
        return None
    center = tuple(sum(coords[i][axis] for i in TORSO) / 4 for axis in (0, 1))
    quality = sum(min(_value(points[i], "visibility"), _value(points[i], "presence")) for i in coords)
    return {"points": coords, "center": center, "scale": scale, "quality": quality / len(coords)}


def duplicate_geometry(a, b):
    """Require torso AND independent upper/lower joint agreement, never just overlap."""
    if a is None or b is None:
        return {"match": False, "reason": "unreliable_geometry"}
    scale = min(a["scale"], b["scale"])
    shared = [i for i in SUPPORT if i in a["points"] and i in b["points"]]
    metrics = {
        "scale_ratio": max(a["scale"], b["scale"]) / scale,
        "center_distance": math.dist(a["center"], b["center"]) / scale,
        "shared_support": len(shared),
    }
    distances = [math.dist(a["points"][i], b["points"][i]) / scale for i in TORSO]
    metrics.update(torso_mean_distance=sum(distances) / 4, torso_max_distance=max(distances))
    support = [math.dist(a["points"][i], b["points"][i]) / scale for i in shared]
    # Lack of common support is evidence of ambiguity, not permission to merge.
    sufficient = (
        len(shared) >= DUPLICATE_THRESHOLDS["shared_support_min"]
        and any(i in UPPER_SUPPORT for i in shared)
        and any(i in LOWER_SUPPORT for i in shared)
    )
    if sufficient:
        metrics.update(
            support_median_distance=float(np.median(support)),
            support_close_fraction=sum(
                d <= DUPLICATE_THRESHOLDS["support_close_distance_max"] for d in support
            )
            / len(support),
        )
    match = (
        sufficient
        and metrics["scale_ratio"] <= DUPLICATE_THRESHOLDS["scale_ratio_max"]
        and metrics["center_distance"] <= DUPLICATE_THRESHOLDS["center_distance_max"]
        and metrics["torso_mean_distance"] <= DUPLICATE_THRESHOLDS["torso_mean_distance_max"]
        and metrics["torso_max_distance"] <= DUPLICATE_THRESHOLDS["torso_max_distance_max"]
        and metrics["support_median_distance"] <= DUPLICATE_THRESHOLDS["support_median_distance_max"]
        and metrics["support_close_fraction"] >= DUPLICATE_THRESHOLDS["support_close_fraction_min"]
    )
    return {
        "match": match,
        "reason": "matching_body_geometry" if match else "distinct_or_unproven",
        **metrics,
    }


def track_geometry(previous, current, reacquiring=False):
    """Conservative geometric continuity; this is not person identification."""
    if previous is None or current is None:
        return {"match": False, "reason": "unreliable_geometry"}
    scale = min(previous["scale"], current["scale"])
    offsets = []
    absolute = []
    for i in TORSO:
        a, b = previous["points"][i], current["points"][i]
        absolute.append(math.dist(a, b) / scale)
        ac = tuple(a[axis] - previous["center"][axis] for axis in (0, 1))
        bc = tuple(b[axis] - current["center"][axis] for axis in (0, 1))
        offsets.append(math.dist(ac, bc) / scale)
    metrics = {
        "scale_ratio": max(previous["scale"], current["scale"]) / scale,
        "center_distance": math.dist(previous["center"], current["center"]) / scale,
        "torso_mean_distance": sum(absolute) / 4,
        "centered_torso_distance": max(offsets),
    }
    limits = REACQUIRE_THRESHOLDS if reacquiring else TRACK_THRESHOLDS
    match = all(
        metrics[key] <= limit
        for key, limit in (
            ("scale_ratio", limits["scale_ratio_max"]),
            ("center_distance", limits["center_distance_max"]),
            ("torso_mean_distance", limits["torso_mean_distance_max"]),
            ("centered_torso_distance", limits["centered_torso_distance_max"]),
        )
    )
    return {
        "match": match,
        "reason": "geometry_continuous" if match else "geometry_discontinuous",
        "gate": "gap_reacquisition" if reacquiring else "adjacent_observation",
        **metrics,
    }


def sample_poses(poses, width, height, stamp):
    """Collapse only well-supported duplicate outputs; distinct people stay ambiguous."""
    geometries = [pose_geometry(points, width, height) for points in poses]
    comparisons, groups = {}, []
    for index in range(len(poses)):
        for other in range(index):
            comparisons[(other, index)] = duplicate_geometry(geometries[other], geometries[index])
        # Complete-link clustering prevents A~B~C chains from merging distinct A/C bodies.
        group = next((g for g in groups if all(comparisons[(i, index)]["match"] for i in g)), None)
        if group is None:
            groups.append([index])
        else:
            group.append(index)
    row = {
        "time_us": stamp,
        "people_detected": len(poses),
        "distinct_pose_count": len(groups),
        "pose_groups": groups,
        "selected_pose_index": None,
        "pose_geometry": None,
        "left": None,
        "right": None,
        "anomaly_codes": [],
        "duplicate_comparisons": [
            {"pose_indices": list(pair), **value} for pair, value in comparisons.items()
        ],
    }
    if not poses:
        row.update(selection="no_pose", anomaly_codes=["pose_missing"])
        return row
    if len(groups) != 1:
        row.update(selection="ambiguous_people", anomaly_codes=["ambiguous_people"])
        return row
    index = max(groups[0], key=lambda i: geometries[i]["quality"] if geometries[i] else -1)
    if geometries[index] is None:
        row.update(selection="unreliable_geometry", anomaly_codes=["unreliable_pose_geometry"])
        return row
    row.update(
        selected_pose_index=index,
        pose_geometry=geometries[index],
        selection="duplicate_cluster" if len(poses) > 1 else "single_pose",
    )
    if len(poses) > 1:
        row["anomaly_codes"].append("duplicate_pose_merged")
    row["wrist_quality"] = {}
    points = poses[index]
    for side, shoulder_id, wrist_id, hip_id in (("left", 11, 15, 23), ("right", 12, 16, 24)):
        shoulder, wrist, hip = [points[i] for i in (shoulder_id, wrist_id, hip_id)]
        span = _value(hip, "y") - _value(shoulder, "y")
        valid = all(_reliable(p) for p in (shoulder, wrist, hip)) and span > 0.06
        quality = {
            "valid": valid,
            "torso_vertical_span": span,
            "visibility": _finite(_value(wrist, "visibility")),
            "presence": _finite(_value(wrist, "presence")),
        }
        row["wrist_quality"][side] = quality
        row[side] = (_value(shoulder, "y") - _value(wrist, "y")) / span if valid else None
    if any(row[side] is None for side in ("left", "right")):
        row["anomaly_codes"].append("wrist_unreliable")
    return row


def evaluate_samples(samples, duration_us):
    candidates, trace, anomaly_events, recent = [], [], [], []
    counts = Counter()
    low, side_last = {}, {}
    peak, last_good, previous_geometry = None, None, None
    last_peak, previous_stamp = -3_000_000, None
    gap, epoch = False, 0
    frame_codes = []

    def anomaly(stamp, code, decision):
        event = {"time_us": stamp, "code": code, "decision": decision}
        if code not in frame_codes:
            frame_codes.append(code)
        if not any(e["time_us"] == stamp and e["code"] == code for e in recent):
            counts[code] += 1
            recent.append(event)
            if len(anomaly_events) < ANOMALY_LIMIT:
                anomaly_events.append(event)

    def emit(stamp, decision):
        nonlocal peak, last_peak, low, side_last, recent
        if peak is None:
            return
        events = [e for e in recent if e["time_us"] >= peak["start_us"]]
        point = peak["time_us"]
        candidates.append(
            {
                "id": ident("candidate"),
                "start_us": max(0, point - 2_000_000),
                "end_us": min(duration_us, point + 2_000_000),
                "peak_us": point,
                "status": "proposed",
                "evidence": {
                    "method": METHOD,
                    "side": peak["side"],
                    "sample_rate_hz": 5,
                    "label": "Wrist-rise motion only; review the interval and any tracking uncertainty.",
                    "shot_verified": False,
                    "all_shots_found": False,
                    "quality": "uncertain_motion_proposal" if events else "motion_proposal",
                    "anomalies": events[:32],
                    "anomaly_count": len(events),
                    "anomalies_truncated": len(events) > 32,
                    "decision": decision,
                    "decision_time_us": stamp,
                    "track_epoch": peak["epoch"],
                    "rise_start_us": peak["start_us"],
                    "peak_height_torso_lengths": peak["height"],
                },
            }
        )
        last_peak, peak, low, side_last, recent = point, None, {}, {}, []

    for row in samples:
        frame_codes = []
        stamp = row["time_us"]
        if previous_stamp is not None and stamp <= previous_stamp:
            raise ValueError("scan_timestamps_not_increasing")
        previous_stamp = stamp
        # Keep bounded recent evidence for a not-yet-qualified rise, retaining all of an active rise.
        since = peak["start_us"] if peak else stamp - MAX_RISE_US
        recent = [e for e in recent if e["time_us"] >= since]
        decisions = []
        for code in row.get("anomaly_codes", []):
            anomaly(stamp, code, row.get("selection", "observation_unavailable"))
        selected = row.get("distinct_pose_count", row.get("people_detected")) == 1
        usable = selected and any(row.get(side) is not None for side in ("left", "right"))
        elapsed = stamp - last_good if last_good is not None else None
        geometry = row.get("pose_geometry")
        gate = {"reason": "no_usable_pose", "match": False}
        if last_good is not None and elapsed > MAX_GAP_US:
            anomaly(stamp, "observation_gap_timeout", "preserve_qualified_peak_and_reset_history")
            emit(stamp, "preserved_on_gap_timeout")
            low, side_last, previous_geometry, last_good = {}, {}, None, None
            gap = False
            epoch += 1
            decisions.append("reset_after_long_gap")
        if usable:
            if previous_geometry is not None:
                reacquiring = gap or (elapsed is not None and elapsed > SAMPLE_INTERVAL_US * 1.5)
                gate = track_geometry(previous_geometry, geometry, reacquiring=reacquiring)
                if not gate["match"]:
                    anomaly(stamp, "identity_discontinuity", "preserve_qualified_peak_and_start_new_track")
                    emit(stamp, "preserved_on_identity_change")
                    low, side_last, recent = {}, {}, []
                    epoch += 1
                    gap = False
                    decisions.append("start_new_track")
                elif gap or (elapsed is not None and elapsed > SAMPLE_INTERVAL_US * 1.5):
                    anomaly(stamp, "short_gap_bridged", "continue_only_after_geometry_match")
                    decisions.append("resume_same_geometry")
            else:
                # Scalar-only rows support already-associated synthetic/unit-test tracks.
                # Production rows always carry reliable geometry before becoming usable.
                gate = {"reason": "new_track" if geometry else "preassociated_scalar_track", "match": True}
                if gap:
                    low, side_last = {}, {}
            previous_geometry, last_good, gap = geometry, stamp, False
            raised = []
            for side in ("left", "right"):
                value = row.get(side)
                if value is None:
                    # Preserve v1's conservative per-wrist gate: missing wrist
                    # evidence cannot seed an unqualified future rise. An already
                    # qualified peak is retained independently of this history.
                    low.pop(side, None)
                    continue
                if side in side_last and stamp - side_last[side] > MAX_GAP_US:
                    low.pop(side, None)
                    anomaly(stamp, "wrist_gap_timeout", "reset_side_low_history")
                side_last[side] = stamp
                if value < 0:
                    low[side] = stamp
                if value >= 0.35 and 0 < stamp - low.get(side, -10_000_000) <= MAX_RISE_US:
                    raised.append((value, side))
            if raised and stamp - last_peak >= 2_000_000:
                value, side = max(raised)
                if peak is None:
                    peak = {
                        "time_us": stamp,
                        "side": side,
                        "height": value,
                        "start_us": low[side],
                        "epoch": epoch,
                    }
                    decisions.append("qualified_rise")
                elif value > peak["height"]:
                    peak.update(time_us=stamp, side=side, height=value)
                    decisions.append("updated_peak")
            if peak and (not raised or stamp - peak["time_us"] > 1_000_000):
                if row.get(peak["side"]) is None:
                    anomaly(stamp, "peak_wrist_unavailable", "preserve_qualified_peak_with_uncertainty")
                emit(stamp, "finalized_after_observation")
                decisions.append("emitted_candidate")
        else:
            if not row.get("anomaly_codes"):
                anomaly(
                    stamp,
                    "ambiguous_people" if row.get("people_detected", 0) > 1 else "pose_missing",
                    "hold_qualified_peak_up_to_gap_limit",
                )
            gap = True
            decisions.append("hold_short_gap" if last_good is not None else "wait_for_track")
        if len(trace) < TRACE_LIMIT:
            trace.append(
                {
                    "time_us": stamp,
                    "raw_pose_count": row.get("people_detected", 0),
                    "distinct_pose_count": row.get("distinct_pose_count", row.get("people_detected", 0)),
                    "selection": row.get("selection", "scalar_input"),
                    "selected_pose_index": row.get("selected_pose_index"),
                    "pose_groups": row.get("pose_groups", []),
                    "duplicate_comparisons": row.get("duplicate_comparisons", []),
                    "identity_gate": gate,
                    "track_epoch": epoch,
                    "gap_since_last_good_us": elapsed,
                    "left": row.get("left"),
                    "right": row.get("right"),
                    "wrist_quality": row.get("wrist_quality", {}),
                    "anomaly_codes": list(frame_codes),
                    "decisions": decisions,
                    "pending_peak_us": peak["time_us"] if peak else None,
                }
            )
    if peak:
        end = previous_stamp if previous_stamp is not None else duration_us
        anomaly(end, "incomplete_end_context", "preserve_qualified_peak_at_eof")
        emit(end, "preserved_at_eof")
    return {
        "candidates": candidates,
        "anomaly_counts": dict(counts),
        "anomaly_events": anomaly_events,
        "anomaly_events_truncated": sum(counts.values()) > len(anomaly_events),
        "decision_trace": trace,
        "decision_trace_limit": TRACE_LIMIT,
        "decision_trace_truncated": len(samples) > len(trace),
        "decision_trace_coverage_us": [trace[0]["time_us"], trace[-1]["time_us"]] if trace else None,
    }


def propose_candidates(samples, duration_us):
    return evaluate_samples(samples, duration_us)["candidates"]


def scan_video(settings, video, progress=None, cancelled=None):
    model = settings.data_dir / "models/pose_landmarker_full.task"
    if not model.is_file():
        raise ValueError("pose_model_missing")
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(
            model_asset_path=str(model), delegate=python.BaseOptions.Delegate.CPU
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=2,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    samples, next_sample, last_ms, decoded = [], 0, -1, 0
    origin = Fraction(video["raw_pts_origin"])
    with (
        av.open(str(settings.resolve(video["original_path"]))) as container,
        vision.PoseLandmarker.create_from_options(options) as landmarker,
    ):
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            if cancelled and cancelled():
                raise InterruptedError("cancelled")
            decoded += 1
            if frame.pts is None:
                continue
            stamp = round((frame.pts * frame.time_base - origin) * 1_000_000)
            if stamp < next_sample:
                continue
            next_sample = stamp + SAMPLE_INTERVAL_US
            rgb = frame.to_ndarray(format="rgb24")
            rotation = getattr(frame, "rotation", 0)
            if rotation:
                rgb = np.ascontiguousarray(np.rot90(rgb, round(rotation / 90)))
            height, width = rgb.shape[:2]
            scale = min(1, 640 / max(height, width))
            if scale < 1:
                rgb = cv2.resize(rgb, (round(width * scale), round(height * scale)))
            ms = max(last_ms + 1, round(stamp / 1000))
            last_ms = ms
            result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
            samples.append(sample_poses(result.pose_landmarks, rgb.shape[1], rgb.shape[0], stamp))
            if progress and len(samples) % 10 == 0:
                progress(min(stamp, video["duration_us"]), video["duration_us"])
    if progress:
        progress(video["duration_us"], video["duration_us"])
    result = evaluate_samples(samples, video["duration_us"])
    return {
        "candidates": result.pop("candidates"),
        "scan_evidence": {
            "method": METHOD,
            "sample_rate_hz": 5,
            "samples": len(samples),
            "decoded_frames": decoded,
            "single_person_samples": sum(s["people_detected"] == 1 for s in samples),
            "resolved_single_person_samples": sum(s["selected_pose_index"] is not None for s in samples),
            "coverage_us": [0, video["duration_us"]],
            "all_shots_found": False,
            "parameters": {
                "max_gap_us": MAX_GAP_US,
                "max_rise_us": MAX_RISE_US,
                "duplicate_geometry": DUPLICATE_THRESHOLDS,
                "track_geometry": TRACK_THRESHOLDS,
                "gap_reacquisition_geometry": REACQUIRE_THRESHOLDS,
            },
            "limitations": [
                "Wrist rises can be passes or non-shot motion.",
                "Duplicate grouping and track continuity are geometric heuristics, not verified person identity.",
                "Occlusion, multiple people, camera motion and quick actions can be missed.",
                "Uncertain qualified motion is retained for review; every proposal needs human confirmation.",
            ],
            **result,
        },
    }

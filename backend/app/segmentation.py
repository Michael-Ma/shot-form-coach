"""Local wrist-rise proposals. These are review candidates, never shot counts."""

from __future__ import annotations

from fractions import Fraction

import av
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .db import ident

METHOD = "local_pose_wrist_rise_v1"


def propose_candidates(samples, duration_us):
    """Require a recent low-to-high wrist transition and ignore ambiguous people."""
    candidates, low, peak = [], {}, None
    last_peak = -3_000_000
    for sample in samples:
        stamp = sample["time_us"]
        if sample.get("people_detected") != 1:
            low, peak = {}, None
            continue
        raised = []
        for side in ("left", "right"):
            value = sample.get(side)
            if value is None:
                low.pop(side, None)
                continue
            if value < 0:
                low[side] = stamp
            if value >= 0.35 and 0 < stamp - low.get(side, -10_000_000) <= 2_500_000:
                raised.append((value, side))
        if raised and stamp - last_peak >= 2_000_000:
            value, side = max(raised)
            if peak is None or value > peak["height"]:
                peak = {"time_us": stamp, "side": side, "height": value}
        # Finalize a rise once it settles; sampling gaps cannot silently sustain it.
        if peak and (not raised or stamp - peak["time_us"] > 1_000_000):
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
                        "label": "Wrist-rise motion only; confirm the shot and adjust the interval.",
                        "shot_verified": False,
                        "all_shots_found": False,
                    },
                }
            )
            last_peak, peak, low = point, None, {}
    # A rise cut off at EOF is retained as an explicitly unconfirmed candidate.
    if peak:
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
                    "label": "Wrist rise near the end; review incomplete context.",
                    "shot_verified": False,
                    "all_shots_found": False,
                },
            }
        )
    return candidates


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
            next_sample = stamp + 200_000
            rgb = frame.to_ndarray(format="rgb24")
            rotation = getattr(frame, "rotation", 0)
            if rotation:
                # Display-matrix rotation is counterclockwise, as is numpy.rot90.
                rgb = np.ascontiguousarray(np.rot90(rgb, round(rotation / 90)))
            height, width = rgb.shape[:2]
            scale = min(1, 640 / max(height, width))
            if scale < 1:
                rgb = cv2.resize(rgb, (round(width * scale), round(height * scale)))
            ms = max(last_ms + 1, round(stamp / 1000))
            last_ms = ms
            result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
            row = {"time_us": stamp, "people_detected": len(result.pose_landmarks)}
            if len(result.pose_landmarks) == 1:
                points = result.pose_landmarks[0]
                for side, shoulder_id, wrist_id, hip_id in (("left", 11, 15, 23), ("right", 12, 16, 24)):
                    shoulder, wrist, hip = [points[i] for i in (shoulder_id, wrist_id, hip_id)]
                    span = hip.y - shoulder.y
                    visible = all(p.visibility >= 0.6 and p.presence >= 0.6 for p in (shoulder, wrist, hip))
                    row[side] = (shoulder.y - wrist.y) / span if visible and span > 0.06 else None
            samples.append(row)
            if progress and len(samples) % 10 == 0:
                progress(min(stamp, video["duration_us"]), video["duration_us"])
    if progress:
        progress(video["duration_us"], video["duration_us"])
    return {
        "candidates": propose_candidates(samples, video["duration_us"]),
        "scan_evidence": {
            "method": METHOD,
            "sample_rate_hz": 5,
            "samples": len(samples),
            "decoded_frames": decoded,
            "single_person_samples": sum(s["people_detected"] == 1 for s in samples),
            "coverage_us": [0, video["duration_us"]],
            "all_shots_found": False,
            "limitations": [
                "Wrist rises can be passes or non-shot motion.",
                "Occlusion, multiple people, camera motion and quick actions can be missed.",
                "Every proposed interval needs human review; add missed clips manually.",
            ],
        },
    }

from __future__ import annotations

import math
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

JOINTS = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_index": 19,
    "right_index": 20,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
}
CONNECTIONS = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
]


def visible(point):
    return point and point.get("visibility", 0) >= 0.5 and 0 <= point["x"] <= 1 and 0 <= point["y"] <= 1


def joint(frame, name):
    points = frame.get("landmarks") or []
    return points[JOINTS[name]] if len(points) > JOINTS[name] else None


def angle(frame, side):
    points = [joint(frame, side + "_" + p) for p in ["shoulder", "elbow", "wrist"]]
    if not all(visible(p) for p in points):
        return None
    coordinates = [np.array([p["x"] * frame["width"], p["y"] * frame["height"]]) for p in points]
    a, b = coordinates[0] - coordinates[1], coordinates[2] - coordinates[1]
    if np.linalg.norm(a) * np.linalg.norm(b) < 1e-6:
        return None
    return float(
        math.degrees(math.acos(np.clip(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)))
    )


class BallDetector:
    """YOLOX COCO sports-ball candidates; decoded as described by OpenCV Zoo.

    Model/source attribution and Apache notice are in models/YOLOX-LICENSE.
    Detection scores are not calibrated contact/release accuracy.
    """

    def __init__(self, path: Path):
        self.net = cv2.dnn.readNet(str(path))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        grids, scales = [], []
        for stride in [8, 16, 32]:
            x, y = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride))
            g = np.stack([x, y], -1).reshape(-1, 2)
            grids.append(g)
            scales.append(np.full((len(g), 1), stride))
        self.grid, self.scale = np.concatenate(grids), np.concatenate(scales)

    def detect(self, bgr, box=None, previous=None):
        h, w = bgr.shape[:2]
        x0, y0, x1, y1 = box or (0, 0, w, h)
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
        roi = bgr[y0:y1, x0:x1]
        if not roi.size:
            return None
        rh, rw = roi.shape[:2]
        scale = min(640 / rw, 640 / rh)
        canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
        canvas[: round(rh * scale), : round(rw * scale)] = cv2.resize(
            roi, (round(rw * scale), round(rh * scale))
        )
        self.net.setInput(np.transpose(canvas.astype(np.float32), (2, 0, 1))[None])
        raw = self.net.forward()[0]
        # COCO category 32 is sports ball. Decode only its plausible candidates.
        scores = raw[:, 4] * raw[:, 5 + 32]
        keep = np.where(scores >= 0.12)[0]
        if not len(keep):
            return None
        selected = raw[keep].copy()
        centers = (selected[:, :2] + self.grid[keep]) * self.scale[keep]
        sizes = np.exp(np.clip(selected[:, 2:4], -10, 10)) * self.scale[keep]
        candidates = []
        for index, center, size in zip(keep, centers, sizes):
            cx, cy = x0 + center[0] / scale, y0 + center[1] / scale
            bw, bh = size / scale
            if not (0 <= cx < w and 0 <= cy < h) or min(bw, bh) < 3:
                continue
            radius = float((bw + bh) / 4)
            if radius > 0.16 * min(w, h):
                continue
            proximity = (
                1
                if not previous
                else max(0.05, 1 - math.hypot(cx - previous["x"] * w, cy - previous["y"] * h) / (h * 0.7))
            )
            candidates.append(
                (
                    float(scores[index]) * proximity,
                    {
                        "x": float(cx / w),
                        "y": float(cy / h),
                        "radius_px": radius,
                        "score": float(scores[index]),
                        "source": "yolox_candidate",
                    },
                )
            )
        return max(candidates, key=lambda c: c[0])[1] if candidates else None


def analyze(settings, asset, progress=None, cancelled=None):
    pose_file = settings.data_dir / "models/pose_landmarker_full.task"
    ball_file = settings.data_dir / "models/yolox_s.onnx"
    if not pose_file.is_file() or not ball_file.is_file():
        raise ValueError("models_missing")
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(
            model_asset_path=str(pose_file), delegate=python.BaseOptions.Delegate.CPU
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=2,
        min_pose_detection_confidence=0.4,
        min_pose_presence_confidence=0.4,
        min_tracking_confidence=0.4,
    )
    detector = BallDetector(ball_file)
    tracks, last_box, last_ball, last_ms = [], None, None, -1
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        for index, frame in enumerate(asset["frame_index"]):
            if cancelled and cancelled():
                raise InterruptedError("cancelled")
            bgr = cv2.imread(str(settings.resolve(frame["path"])))
            if bgr is None:
                raise ValueError("frame_unavailable")
            height, width = bgr.shape[:2]
            stamp = max(last_ms + 1, round(frame["time_us"] / 1000))
            last_ms = stamp
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)), stamp
            )
            choices = []
            for landmarks in result.pose_landmarks:
                points = [
                    {
                        "x": float(p.x),
                        "y": float(p.y),
                        "z_estimate": float(p.z),
                        "visibility": float(p.visibility),
                        "presence": float(p.presence),
                    }
                    for p in landmarks
                ]
                body = [p for p in points if visible(p)]
                if len(body) < 8:
                    continue
                xs, ys = [p["x"] for p in body], [p["y"] for p in body]
                box = [min(xs) * width, min(ys) * height, max(xs) * width, max(ys) * height]
                area = (box[2] - box[0]) * (box[3] - box[1])
                continuity = 1
                if last_box:
                    distance = math.hypot(
                        (box[0] + box[2] - last_box[0] - last_box[2]) / 2,
                        (box[1] + box[3] - last_box[1] - last_box[3]) / 2,
                    )
                    continuity = max(0.15, 1 - distance / height)
                choices.append((area * continuity, points, box))
            points, box = (None, None) if not choices else max(choices, key=lambda p: p[0])[1:]
            if box:
                last_box = box
                bh = box[3] - box[1]
                roi = [box[0] - 0.45 * bh, box[1] - 0.4 * bh, box[2] + 0.25 * bh, box[3] + 0.08 * bh]
            else:
                roi = None
            ball = detector.detect(bgr, roi, last_ball)
            if ball:
                last_ball = ball
            tracks.append(
                {
                    "frame_index": index,
                    "frame_id": frame["frame_id"],
                    "time_us": frame["time_us"],
                    "source_time_us": frame["source_time_us"],
                    "width": width,
                    "height": height,
                    "landmarks": points,
                    "person_box": box,
                    "ball": ball,
                    "people_detected": len(result.pose_landmarks),
                }
            )
            if progress and (index % 5 == 0 or index == len(asset["frame_index"]) - 1):
                progress(index + 1, len(asset["frame_index"]))
    return {
        "version": "mediapipe-1.1.0+opencv-yolox-v1",
        "frames": tracks,
        "coordinate_system": "normalized_image_projection",
        "world_coordinates_validated": False,
    }

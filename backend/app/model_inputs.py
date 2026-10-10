"""Complement full-scene context with fixed, native-resolution person crops.

Views share original frame IDs/timestamps; image count remains inside the caller's cap.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import av
from PIL import Image

VERSION = "context-and-body-v1"


def choose(frames, count, priority=()):
    if len(frames) <= count:
        return list(frames)
    indices = {round(i * (len(frames) - 1) / (count - 1)) for i in range(count)} if count > 1 else {0}
    wanted = {i for i, frame in enumerate(frames) if frame["frame_index"] in priority}
    for index in sorted(wanted):
        if index not in indices:
            removable = [i for i in indices if i not in wanted and i not in (0, len(frames) - 1)]
            if not removable:
                break
            indices.remove(min(removable, key=lambda i: abs(i - index)))
            indices.add(index)
    return [frames[i] for i in sorted(indices)]


def prepare_model_frames(settings, asset, maximum, folder, fallback):
    frames = asset["frame_index"]
    baseline = [{**f, "view": "full_scene"} for f in fallback(asset, maximum)]
    plan = {
        "version": VERSION,
        "frame_limit": maximum,
        "views": {"full_scene": len(baseline), "body_detail": 0},
        "focus_available": False,
        "warnings": [],
    }
    if not frames or not asset.get("tracks_path") or not asset.get("original_path"):
        plan["warnings"].append("body_crop_unavailable")
        return baseline, plan
    try:
        track = json.loads(settings.resolve(asset["tracks_path"]).read_text())
        release = asset.get("phases", {}).get("release") or asset.get("phases", {}).get("extension_peak")
        anchor = sum(release["range_us"]) / 2 if release else None
        active = [
            f for f in frames if anchor is None or anchor - 1_500_000 <= f["time_us"] <= anchor + 1_200_000
        ]
        selected_ids = {f["frame_index"] for f in active}
        boxes = [
            f["person_box"]
            for f in track["frames"]
            if f["frame_index"] in selected_ids and f.get("person_box")
        ]
        if len(boxes) < 5:
            raise ValueError("body_crop_unavailable")
        width, height = asset["width"], asset["height"]
        if any(not all(math.isfinite(v) for v in box) for box in boxes):
            raise ValueError("body_crop_unavailable")
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        padding = (y1 - y0) * 0.23
        box = [
            max(0, math.floor(x0 - padding)),
            max(0, math.floor(y0 - padding)),
            min(width, math.ceil(x1 + padding)),
            min(height, math.ceil(y1 + padding)),
        ]
        if (
            min(box[2] - box[0], box[3] - box[1]) < 40
            or (box[2] - box[0]) * (box[3] - box[1]) > width * height * 0.85
        ):
            raise ValueError("body_crop_not_useful")
        context_count = max(2, min(12, maximum // 3))
        priority = release.get("frame_range", []) if release else []
        context = [{**f, "view": "full_scene"} for f in choose(frames, context_count, priority)]
        focus = choose(
            active,
            maximum - len(context),
            range(max(0, int(priority[0]) - 2), int(priority[-1]) + 3) if priority else (),
        )
        if not focus:
            raise ValueError("body_crop_unavailable")
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        needed = {f["frame_index"]: f for f in focus}
        crops = []
        with av.open(str(settings.resolve(asset["original_path"]))) as container:
            for index, frame in enumerate(container.decode(video=0)):
                if index > max(needed):
                    break
                if index not in needed:
                    continue
                im = frame.to_image()
                rotation = getattr(frame, "rotation", 0)
                if rotation:
                    im = im.rotate(round(rotation / 90) * 90, expand=True)
                if abs(im.width / im.height - width / height) > 0.02:
                    raise ValueError("body_crop_orientation_unavailable")
                native_box = [
                    round(box[0] * im.width / width),
                    round(box[1] * im.height / height),
                    round(box[2] * im.width / width),
                    round(box[3] * im.height / height),
                ]
                crop = im.crop(native_box)
                crop.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                path = folder / f"body-{index:05d}.jpg"
                crop.save(path, quality=92)
                crops.append(
                    {
                        **needed[index],
                        "path": str(path.relative_to(settings.data_dir)),
                        "view": "body_detail",
                        "crop_box_original_px": native_box,
                        "original_size_px": list(im.size),
                        "image_size_px": list(crop.size),
                    }
                )
        if len(crops) != len(focus):
            raise ValueError("body_crop_frame_mapping_failed")
        output = sorted(context + crops, key=lambda f: (f["time_us"], f["view"]))
        plan.update(
            focus_available=True,
            views={"full_scene": len(context), "body_detail": len(crops)},
            focus_source="local_person_track",
            fixed_crop_preview_px=box,
            focus_range_us=[active[0]["time_us"], active[-1]["time_us"]],
            distinct_source_frames=len({f["frame_id"] for f in output}),
            detail_limit="A crop exposes original pixels; unseen fingers, depth and force remain unknown.",
        )
        return output, plan
    except (OSError, ValueError, KeyError, IndexError, av.error.FFmpegError) as exc:
        plan["warnings"].append(str(exc) if isinstance(exc, ValueError) else "body_crop_unavailable")
        return baseline, plan

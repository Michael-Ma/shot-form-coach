from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

from PIL import Image

from .db import ident, now


class MediaError(ValueError):
    pass


def run(args, timeout=120):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise MediaError(result.stderr[-2000:])
    return result.stdout


def probe(path):
    raw = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-show_frames",
                "-show_entries",
                "stream=width,height,codec_name:frame=best_effort_timestamp_time,pkt_duration_time",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    if not raw.get("streams") or not raw.get("frames"):
        raise MediaError("No usable video frames")
    times = [round(Decimal(f["best_effort_timestamp_time"]) * 1_000_000) for f in raw["frames"]]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise MediaError("Video timestamps are not strictly increasing")
    origin = times[0]
    delta = round(Decimal(raw["frames"][-1].get("pkt_duration_time", "0")) * 1_000_000)
    if delta <= 0:
        delta = times[-1] - times[-2] if len(times) > 1 else 33333
    duration = times[-1] - origin + delta
    if duration > 30_000_000 or len(times) > 1800:
        raise MediaError("Import a single shooting clip of at most 30 seconds")
    return raw["streams"][0], [t - origin for t in times], duration, origin


def ingest(settings, repo, path: Path, filename: str, upstream=None, label=None):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    upstream = upstream or {}
    for record in repo.all("asset"):
        if record["sha256"] == digest and record.get("upstream") == upstream:
            return record
    stream, times, duration, raw_origin = probe(path)
    key = ident("shot")
    folder = settings.data_dir / "assets" / key
    folder.mkdir(parents=True)
    source = folder / "original"
    shutil.copyfile(path, source)
    preview = folder / "preview.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-an",
            "-vf",
            "setpts=PTS-STARTPTS,scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "passthrough",
            "-enc_time_base",
            "1/1000000",
            "-video_track_timescale",
            "1000000",
            "-movflags",
            "+faststart",
            str(preview),
        ]
    )
    _, preview_times, _, _ = probe(preview)
    if len(times) != len(preview_times) or any(abs(a - b) > 1000 for a, b in zip(times, preview_times)):
        raise MediaError("Preview timing does not match the source frames")
    frames_folder = folder / "frames"
    frames_folder.mkdir()
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-fps_mode",
            "passthrough",
            "-q:v",
            "3",
            str(frames_folder / "%05d.jpg"),
        ]
    )
    files = sorted(frames_folder.glob("*.jpg"))
    if len(files) != len(times):
        raise MediaError("Decoded frame count does not match its timestamp index")
    width, height = Image.open(files[0]).size
    source_offset = upstream.get("source_start_us", 0)
    source_first = upstream.get("source_first_frame_index")
    frame_index = [
        {
            "frame_index": n,
            "time_us": t,
            "source_time_us": source_offset + t,
            "source_frame_index": source_first + n if source_first is not None else None,
            "frame_id": f"{digest[:16]}:frame:{n}",
            "path": str(files[n].relative_to(settings.data_dir)),
        }
        for n, t in enumerate(times)
    ]
    record = {
        "id": key,
        "label": label or filename,
        "filename": filename,
        "sha256": digest,
        "created_at": now(),
        "updated_at": now(),
        "revision": 0,
        "status": "ready",
        "duration_us": duration,
        "width": width,
        "height": height,
        "source_width": stream["width"],
        "source_height": stream["height"],
        "raw_pts_origin_us": raw_origin,
        "preview_path": str(preview.relative_to(settings.data_dir)),
        "original_path": str(source.relative_to(settings.data_dir)),
        "upstream": upstream,
        "frame_index": frame_index,
        "phases": {},
        "phase_history": [],
        "report": None,
    }
    return repo.put("asset", record)


def import_workbench(settings, repo, run_id):
    if not settings.workbench_data:
        raise MediaError("Workbench data directory is not configured")
    root = settings.workbench_data.resolve()
    run_dir = (root / "runs" / run_id).resolve()
    if not run_dir.is_relative_to(root):
        raise MediaError("Invalid run path")
    results = json.loads((run_dir / "results.json").read_text())
    imported = []
    for index, event in enumerate(results.get("events", [])):
        clip = event.get("clip")
        if not clip or event.get("duplicate_of") or event.get("clip_status") != "succeeded":
            continue
        source = (root / clip["path"]).resolve()
        if not source.is_relative_to(root):
            raise MediaError("Clip path is outside the configured Workbench directory")
        upstream = {
            "run_id": run_id,
            "event_id": event["event_id"],
            "source_start_us": clip["actual_range_us"][0],
            "source_end_us": clip["actual_range_us"][1],
            "source_first_frame_index": clip.get("metadata", {})
            .get("source_first_frame", {})
            .get("frame_index"),
            "camera_group": event["event_id"].split("_")[0] + ":" + run_id,
            "result_bucket": event.get("result_bucket"),
        }
        imported.append(ingest(settings, repo, source, source.name, upstream, label=f"Shot {index + 1}"))
    return imported

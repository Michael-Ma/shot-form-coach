"""Persistent source videos and reversible, source-timestamped clip management."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import av

from .db import ident, now
from .media import MediaError, ingest, probe, run


def metadata(path, max_duration_us):
    raw = json.loads(
        run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], timeout=30)
    )
    stream = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream or stream.get("disposition", {}).get("attached_pic"):
        raise MediaError("invalid_video")
    duration = round(float(stream.get("duration") or raw.get("format", {}).get("duration", 0)) * 1_000_000)
    if duration <= 0:
        raise MediaError("video_duration_unknown")
    if duration > max_duration_us:
        raise MediaError("video_too_long")
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        first = next(container.decode(video), None)
        if first is None or first.pts is None:
            raise MediaError("invalid_video")
        origin = first.pts * first.time_base
        # Container durations can be wrong for VFR/edit lists. Decode only the
        # last GOP to establish the actual last display timestamp.
        container.seek(
            math.floor((origin + Fraction(max(0, duration - 2_000_000), 1_000_000)) / video.time_base),
            stream=video,
            backward=True,
        )
        last, previous = None, None
        deadline = time.monotonic() + 30
        for frame in container.decode(video):
            if time.monotonic() > deadline:
                raise MediaError("video_metadata_timeout")
            if frame.pts is None:
                raise MediaError("frame_timestamp_missing")
            stamp = round((frame.pts * frame.time_base - origin) * 1_000_000)
            if stamp > max_duration_us:
                raise MediaError("video_too_long")
            previous, last = last, (stamp, round((frame.duration or 0) * frame.time_base * 1_000_000))
        if last:
            duration = last[0] + (last[1] or (last[0] - previous[0] if previous else 33333))
        if duration > max_duration_us:
            raise MediaError("video_too_long")
    return {
        "duration_us": duration,
        "width": stream["width"],
        "height": stream["height"],
        "raw_pts_origin_us": round(origin * 1_000_000),
        "raw_pts_origin": str(origin),
    }


def import_video(settings, repo, upload, filename):
    """Stream original bytes to their persistent home; never read an upload wholesale."""
    key = ident("video")
    folder = settings.data_dir / "videos" / key
    folder.mkdir(parents=True)
    original = folder / "original"
    digest, size = hashlib.sha256(), 0
    try:
        with original.open("wb") as output:
            while chunk := upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_video_upload_mb * 1024 * 1024:
                    raise MediaError("upload_too_large")
                digest.update(chunk)
                output.write(chunk)
        if not size:
            raise MediaError("empty_upload")
        info = metadata(original, settings.max_video_duration_us)
        with repo.lock:
            existing = next((v for v in repo.all("video") if v["sha256"] == digest.hexdigest()), None)
            if existing:
                shutil.rmtree(folder)
                return existing
            return repo.put(
                "video",
                {
                    "id": key,
                    "kind": "source",
                    "label": filename,
                    "filename": filename,
                    "sha256": digest.hexdigest(),
                    "size_bytes": size,
                    "created_at": now(),
                    "updated_at": now(),
                    "status": "processing",
                    "revision": 0,
                    "original_path": str(original.relative_to(settings.data_dir)),
                    "preview_path": None,
                    "thumbnail_path": None,
                    "candidates": [],
                    "scan_status": "not_started",
                    **info,
                },
            )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def cancellable_run(args, cancelled, timeout=3600):
    # stderr goes to a bounded-on-read temporary file so ffmpeg cannot block on a full pipe.
    with tempfile.TemporaryFile() as error:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=error)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    raise InterruptedError("cancelled")
                if time.monotonic() - started > timeout:
                    raise MediaError("preview_timeout")
                time.sleep(0.1)
            if process.returncode:
                raise MediaError("video_processing_failed")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def prepare_video(settings, repo, video, cancelled):
    folder = settings.resolve(video["original_path"]).parent
    preview = folder / "preview.mp4"
    temporary = folder / "preview.pending.mp4"
    try:
        cancellable_run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(folder / "original"),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                "setpts=PTS-STARTPTS,scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-pix_fmt",
                "yuv420p",
                "-fps_mode",
                "vfr",
                "-enc_time_base",
                "1:1000000",
                "-video_track_timescale",
                "1000000",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            cancelled,
        )
        if cancelled():
            raise InterruptedError("cancelled")
        temporary.replace(preview)
        thumbnail = folder / "thumbnail.jpg"
        cancellable_run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(preview),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:480:force_original_aspect_ratio=decrease",
                str(thumbnail),
            ],
            cancelled,
            timeout=60,
        )
        return repo.patch(
            "video",
            video["id"],
            status="ready",
            error_code=None,
            preview_path=str(preview.relative_to(settings.data_dir)),
            thumbnail_path=str(thumbnail.relative_to(settings.data_dir)),
        )
    finally:
        temporary.unlink(missing_ok=True)


def session_id(asset):
    upstream = asset.get("upstream") or {}
    return (
        asset.get("video_id")
        or upstream.get("video_id")
        or ("workbench_" + upstream["run_id"] if upstream.get("run_id") else "legacy_standalone")
    )


def asset_bounds(asset):
    upstream = asset.get("upstream") or {}
    start = asset.get("source_start_us", upstream.get("source_start_us", 0))
    end = asset.get("source_end_us", upstream.get("source_end_us", start + asset.get("duration_us", 0)))
    return start, end


def asset_lifecycle(asset):
    start, end = asset_bounds(asset)
    return {
        **asset,
        "session_id": session_id(asset),
        "source_start_us": start,
        "source_end_us": end,
        "trashed_at": asset.get("trashed_at"),
        "superseded_by": asset.get("superseded_by"),
        "lifecycle_revision": asset.get("lifecycle_revision", 0),
    }


def sessions(repo):
    result = {v["id"]: dict(v) for v in repo.all("video")}
    for asset in repo.all("asset"):
        key = session_id(asset)
        if key not in result:
            result[key] = {
                "id": key,
                "kind": "legacy",
                "label": "Earlier clips",
                "filename": None,
                "duration_us": 0,
                "status": "ready",
                "created_at": asset.get("created_at", ""),
                "updated_at": asset.get("updated_at", ""),
                "preview_path": None,
                "candidates": [],
                "scan_status": "unavailable",
                "revision": 0,
            }
        video = result[key]
        video.setdefault("clips", []).append(asset_lifecycle(asset))
        if video["kind"] != "source":
            video["duration_us"] = max(video["duration_us"], asset_bounds(asset)[1])
    for video in result.values():
        video.setdefault("clips", [])
        video["clip_count"] = sum(not a.get("trashed_at") for a in video["clips"])
        video["trashed_count"] = sum(bool(a.get("trashed_at")) for a in video["clips"])
        video["candidate_count"] = sum(c.get("status") == "proposed" for c in video.get("candidates", []))
        video["clips"].sort(key=lambda a: (a["source_start_us"], a.get("created_at", "")))
    return sorted(result.values(), key=lambda v: v.get("created_at", ""), reverse=True)


def selected_frames(source, start_us, end_us, origin):
    """Decode just the selected GOP/range, retaining actual PTS for VFR mapping."""
    selected, after, key_pts = [], None, None
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        container.seek(
            math.floor((origin + Fraction(start_us, 1_000_000)) / stream.time_base),
            stream=stream,
            backward=True,
        )
        for frame in container.decode(stream):
            if frame.pts is None:
                raise MediaError("frame_timestamp_missing")
            stamp = round((frame.pts * frame.time_base - origin) * 1_000_000)
            if key_pts is None:
                key_pts = frame.pts * frame.time_base
            if stamp >= end_us:
                after = stamp
                break
            if stamp >= start_us:
                selected.append(
                    {
                        "pts": frame.pts,
                        "time_base": frame.time_base,
                        "source_time_us": stamp,
                        "duration_us": round((frame.duration or 0) * frame.time_base * 1_000_000),
                    }
                )
    if not selected:
        raise MediaError("no_frames_in_range")
    final = selected[-1]
    end = after or (
        final["source_time_us"]
        + (
            final["duration_us"]
            or (final["source_time_us"] - selected[-2]["source_time_us"] if len(selected) > 1 else 33333)
        )
    )
    if end - selected[0]["source_time_us"] > 30_000_000:
        raise MediaError("clip_frame_span_exceeds_30_seconds")
    return selected, end, key_pts


def cut_asset(settings, repo, source, origin, start_us, end_us, upstream, label):
    selected, actual_end, key_pts = selected_frames(source, start_us, end_us, origin)
    first = selected[0]
    tb = first["time_base"]
    end_pts = math.ceil((origin + Fraction(actual_end, 1_000_000)) / tb)
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "clip.mp4"
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-copyts",
                "-seek_timestamp",
                "1",
                "-ss",
                f"{float(key_pts):.9f}",
                "-noaccurate_seek",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"settb=expr={tb.numerator}/{tb.denominator},trim=start_pts={first['pts']}:end_pts={end_pts},setpts=PTS-STARTPTS,scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-fps_mode",
                "vfr",
                "-enc_time_base",
                "1:1000000",
                "-video_track_timescale",
                "1000000",
                "-frames:v",
                str(len(selected)),
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        times = probe(target)[1]
        expected = [f["source_time_us"] - first["source_time_us"] for f in selected]
        if len(times) != len(expected) or any(abs(a - b) > 1000 for a, b in zip(times, expected)):
            raise MediaError("clip_frame_mapping_failed")
        offset = upstream.pop("timeline_offset_us", 0)
        upstream.update(
            source_start_us=offset + first["source_time_us"],
            source_end_us=offset + actual_end,
            requested_range_us=[offset + start_us, offset + end_us],
        )
        asset = ingest(settings, repo, target, "clip.mp4", upstream=upstream, label=label)
        return repo.patch(
            "asset",
            asset["id"],
            video_id=upstream.get("video_id"),
            source_start_us=upstream["source_start_us"],
            source_end_us=upstream["source_end_us"],
            confirmation="human_confirmed",
            candidate_id=upstream.get("candidate_id"),
        )


def create_clip(settings, repo, video_id, request):
    with repo.lock:
        video = repo.get("video", video_id)
        if request.end_us > video["duration_us"]:
            raise MediaError("range_outside_source")
        candidate = None
        if request.candidate_id:
            candidate = next(
                (c for c in video.get("candidates", []) if c["id"] == request.candidate_id), None
            )
            if not candidate or candidate["status"] != "proposed":
                raise ValueError("candidate_not_proposed")
        clip = cut_asset(
            settings,
            repo,
            settings.resolve(video["original_path"]),
            Fraction(video["raw_pts_origin"]),
            request.start_us,
            request.end_us,
            {"video_id": video_id, "camera_group": video_id, "candidate_id": request.candidate_id},
            request.label
            or f"Shot {sum(session_id(a) == video_id and not a.get('trashed_at') for a in repo.all('asset')) + 1}",
        )
        if candidate:
            candidate.update(status="confirmed", asset_id=clip["id"], confirmed_at=now())
            repo.patch("video", video_id, candidates=video["candidates"])
        return clip


def trim_clip(settings, repo, asset_id, request):
    with repo.lock:
        asset = repo.get("asset", asset_id)
        repo.assert_available(asset, request.expected_revision)
        if asset.get("lifecycle_revision", 0) != request.expected_lifecycle_revision:
            raise ValueError("stale_lifecycle_revision")
        repo.assert_idle(asset_id)
        video_id = asset.get("video_id") or asset.get("upstream", {}).get("video_id")
        if video_id:
            video = repo.get("video", video_id)
            if request.end_us > video["duration_us"]:
                raise MediaError("range_outside_source")
            source = settings.resolve(video["original_path"])
            origin, offset = Fraction(video["raw_pts_origin"]), 0
        else:
            lo, hi = asset_bounds(asset)
            if request.start_us < lo or request.end_us > hi:
                raise MediaError("range_outside_available_clip")
            source = settings.resolve(asset["original_path"])
            origin, offset = Fraction(asset.get("raw_pts_origin_us", 0), 1_000_000), lo
        upstream = {**asset.get("upstream", {}), "supersedes": asset_id, "timeline_offset_us": offset}
        upstream.pop("source_first_frame_index", None)
        new = cut_asset(
            settings,
            repo,
            source,
            origin,
            request.start_us - offset,
            request.end_us - offset,
            upstream,
            request.label or asset["label"],
        )
        new["supersedes"] = asset_id
        asset.update(
            trashed_at=now(),
            superseded_by=new["id"],
            lifecycle_revision=asset.get("lifecycle_revision", 0) + 1,
            updated_at=now(),
        )
        repo.put_many([("asset", new), ("asset", asset)])
        repo.invalidate_dependents(asset_id)
        return new

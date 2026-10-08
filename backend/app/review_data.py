"""Refresh derived measurements from cached tracks without running a model."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .analysis import measure


@lru_cache(maxsize=32)
def _measure_cached(path: str, modified_ns: int, phase_json: str, side: str, side_source: str):
    track = json.loads(Path(path).read_text())
    return measure(track, json.loads(phase_json), side, side_source)


def current_measurements(settings, asset):
    result = dict(asset)
    previous = asset.get("measurements")
    if not previous or not asset.get("tracks_path"):
        return result
    path = settings.resolve(asset["tracks_path"])
    try:
        result["measurements"] = _measure_cached(
            str(path),
            path.stat().st_mtime_ns,
            json.dumps(asset.get("phases") or {}, sort_keys=True),
            previous["side"],
            previous["side_source"],
        )
    except (OSError, ValueError, KeyError):
        result["measurements"] = {
            **previous,
            "flags": sorted(set(previous.get("flags", []) + ["track_unavailable"])),
        }
    return result

import json
import subprocess

import av
import pytest
from app.analysis import current_phases, recent_loading_bottom
from app.coaching import build_review, load_rubric, validate_model_coaching
from app.config import Settings
from app.model_inputs import prepare_model_frames
from app.provider import sampled_frames


def localized(text):
    return {"en": text, "zh": "可见动作证据"}


def review(coverage):
    return {
        "overall_summary": localized("Supported observations."),
        "strengths": [],
        "issues": [],
        "coverage": coverage,
    }


def coverage_rows():
    return [
        {
            "rubric_id": d["id"],
            "status": "aligned",
            "detail": localized("Visible coordinated movement."),
            "evidence_frame_ids": ["f0", "f1"],
        }
        for d in load_rubric()["dimensions"]
    ]


def test_current_remote_review_requires_all_dimensions_while_cached_review_is_preserved():
    old = review(coverage_rows()[:5])
    validate_model_coaching(old, ["f0", "f1"])
    with pytest.raises(ValueError, match="every rubric dimension"):
        validate_model_coaching(old, ["f0", "f1"], require_complete=True)
    validate_model_coaching(review(coverage_rows()), ["f0", "f1"], require_complete=True)


def test_unclear_and_unreviewed_dimensions_cannot_produce_a_global_no_issue_conclusion():
    rows = coverage_rows()
    shot = {
        "id": "a",
        "revision": 0,
        "frame_index": [{"frame_id": "f0"}, {"frame_id": "f1"}],
        "model_assist": {"asset_revision": 0, "coaching": review(rows)},
    }
    result = build_review(shot)
    assert result["outcome"] == "no_priority_issue"
    rows[3]["status"] = "uncertain"
    rows.pop()
    result = build_review(shot)
    assert result["outcome"] == "limited_visibility"
    assert result["coverage"]["assessed_dimensions"] == 7
    assert len(result["coverage"]["missing_dimensions"]) == 1
    assert len(result["coverage"]["uncertain_dimensions"]) == 1
    assert result["overall"]["headline"]["zh"] == "动作检查尚不完整"


def test_shooting_load_excludes_a_deeper_preparation_at_clip_start_and_preserves_manual_correction():
    frames = []
    for i in range(71):
        y = 0.80 if i < 10 else 0.60
        if 49 <= i <= 57:
            y = 0.66 - abs(i - 53) * 0.012
        if i >= 58:
            y = 0.55
        points = [{"x": 0.5, "y": y, "visibility": 1} for _ in range(33)]
        frames.append({"frame_index": i, "time_us": i * 50_000, "landmarks": points})
    track = {"frames": frames}
    loading = recent_loading_bottom(track, 3_000_000)
    assert 2_500_000 <= loading["range_us"][0] <= 2_800_000
    assert loading["frame_range"][0] > 10
    manual = {
        "release": {"range_us": [3_000_000] * 2},
        "loading_bottom": {"source": "user_corrected", "range_us": [100_000] * 2},
    }
    assert current_phases(track, manual)["loading_bottom"] == manual["loading_bottom"]
    assert recent_loading_bottom({"frames": frames[:2]}, 100_000) is None


@pytest.mark.parametrize("vfr", [False, True])
def test_focus_inputs_preserve_source_identity_pixels_and_total_image_budget(tmp_path, vfr):
    s = Settings(tmp_path)
    s.prepare()
    folder = tmp_path / "assets" / "a"
    folder.mkdir()
    src = folder / "source.mp4"
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=20:duration=3"]
    if vfr:
        args += ["-vf", "setpts=if(lt(N\\,20)\\,N\\,20+(N-20)*2)/20/TB"]
    subprocess.run(args + ["-fps_mode", "passthrough", "-c:v", "libx264", str(src)], check=True)
    frames = []
    tracks = []
    with av.open(str(src)) as container:
        for i, f in enumerate(container.decode(video=0)):
            im = f.to_image()
            im.thumbnail((320, 180))
            p = folder / f"{i}.jpg"
            im.save(p)
            stamp = round(f.pts * f.time_base * 1e6)
            frames.append(
                {
                    "frame_id": f"f{i}",
                    "frame_index": i,
                    "time_us": stamp,
                    "source_time_us": 9_000_000 + stamp,
                    "path": str(p.relative_to(tmp_path)),
                }
            )
            tracks.append({"frame_index": i, "person_box": [140, 35, 190, 155]})
    track = folder / "tracks.json"
    track.write_text(json.dumps({"frames": tracks}))
    a = {
        "frame_index": frames,
        "width": 320,
        "height": 180,
        "original_path": str(src.relative_to(tmp_path)),
        "tracks_path": str(track.relative_to(tmp_path)),
        "phases": {
            "release": {"range_us": [frames[30]["time_us"], frames[31]["time_us"]], "frame_range": [30, 31]}
        },
    }
    output, plan = prepare_model_frames(s, a, 20, tmp_path / "receipts" / "a" / "inputs", sampled_frames)
    assert plan["focus_available"] and len(output) <= 20
    assert output[0]["time_us"] == frames[0]["time_us"] and output[-1]["time_us"] == frames[-1]["time_us"]
    by_id = {f["frame_id"]: f for f in frames}
    boxes = []
    for f in output:
        original = by_id[f["frame_id"]]
        assert f["time_us"] == original["time_us"] and f["source_time_us"] == original["source_time_us"]
        assert s.resolve(f["path"]).is_file()
        if f["view"] == "body_detail":
            assert f["original_size_px"] == [640, 360]
            boxes.append(f["crop_box_original_px"])
    assert boxes and all(b == boxes[0] for b in boxes)
    assert plan["views"]["full_scene"] + plan["views"]["body_detail"] == len(output)

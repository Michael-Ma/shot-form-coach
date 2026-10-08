"""Semantic geometry checks: preserved anatomy, honest alignment and quality gates."""

import math
from copy import deepcopy

import pytest
from app.pose_comparison import build_pose_comparison


def fixture(shot_id="own", *, shift_us=0, pixel_scale=1, offset=(0, 0), width=1000, height=800):
    # Deliberately non-square frames detect normalized-coordinate angle mistakes.
    body = {
        11: (360, 350),
        12: (400, 350),
        13: (360, 410),
        14: (430, 250),
        15: (360, 470),
        16: (420, 140),
        23: (370, 500),
        24: (400, 500),
        25: (365, 610),
        26: (405, 610),
        27: (360, 730),
        28: (410, 730),
    }
    frames = []
    for i in range(31):
        points = [None] * 33
        for index, (x, y) in body.items():
            points[index] = {
                "x": (x * pixel_scale + offset[0]) / width,
                "y": (y * pixel_scale + offset[1]) / height,
                "visibility": 0.95,
            }
        frames.append(
            {
                "frame_index": i,
                "frame_id": f"{shot_id}:{i}",
                "time_us": i * 50000 + shift_us,
                "source_time_us": i * 50000 + shift_us + 1234567,
                "width": width,
                "height": height,
                "landmarks": points,
            }
        )
    asset = {
        "id": shot_id,
        "revision": 2,
        "phases": {
            "release": {"range_us": [500000 + shift_us, 550000 + shift_us], "source": "user_corrected"}
        },
        "analysis_config": {"handedness": "right", "shot_type": "set_shot", "camera_view": "side"},
        "measurements": {"side": "right", "side_source": "user_setting"},
        "upstream": {"camera_group": "tripod-1"},
    }
    return asset, {"frames": frames}


def dist(frame, a, b):
    return math.hypot((a["x"] - b["x"]) * frame["width"], (a["y"] - b["y"]) * frame["height"])


def test_teaching_preserves_projected_segment_lengths_and_own_shoulder():
    asset, track = fixture()
    original = deepcopy(track)
    result = build_pose_comparison(asset, track)
    assert result["comparison_status"] == "teaching_illustration"
    assert result["source_type"] == "qualitative_teaching_illustration"
    assert result["scope"] == "shooting_arm_only"
    assert result["grading_thresholds"] is None
    assert result["measured_expert_motion"] is False
    assert result["template_angle_deg"] == 165
    assert result["recommended_frame_index"] in (10, 11)
    for output in result["frames"]:
        if not output["available"]:
            continue
        source = track["frames"][output["frame_index"]]
        own, target = source["landmarks"], output["target_landmarks"]
        assert [i for i, p in enumerate(target) if p] == [12, 14, 16]
        assert target[12]["x"] == own[12]["x"]
        assert target[12]["y"] == own[12]["y"]
        assert dist(source, target[12], target[14]) == pytest.approx(dist(source, own[12], own[14]))
        assert dist(source, target[14], target[16]) == pytest.approx(dist(source, own[14], own[16]))
        assert output["connections"] == [[12, 14], [14, 16]]
        assert all(d["interpretation"] == "descriptive_difference_not_fault_score" for d in output["deltas"])
        assert not any("severity" in d for d in output["deltas"])
        assert output["own_evidence"]["source_time_us"] == source["source_time_us"]
    assert track == original


def test_teaching_has_no_fabricated_pose_before_release_or_when_arm_hidden():
    asset, track = fixture()
    track["frames"][15]["landmarks"][14]["visibility"] = 0.1
    result = build_pose_comparison(asset, track)
    before = result["frames"][0]
    hidden = result["frames"][15]
    assert before["reason"] == "teaching_phase_only"
    assert hidden["reason"] == "arm_not_visible"
    assert hidden["target_landmarks"] == [None] * 33
    assert hidden["deltas"] == []
    assert result["frames"][-1]["reason"] == "teaching_phase_only"


def test_teaching_left_hand_uses_left_landmarks():
    asset, track = fixture()
    asset["analysis_config"]["handedness"] = "left"
    # Mirror the right arm into an elevated visible left shooting arm.
    for f in track["frames"]:
        for left, right in ((11, 12), (13, 14), (15, 16)):
            f["landmarks"][left] = {**f["landmarks"][right], "x": 1 - f["landmarks"][right]["x"]}
    result = build_pose_comparison(asset, track)
    output = next(f for f in result["frames"] if f["available"])
    assert output["connections"] == [[11, 13], [13, 15]]
    assert [i for i, p in enumerate(output["target_landmarks"]) if p] == [11, 13, 15]


@pytest.mark.parametrize(
    "change,reason",
    [
        ("unknown_hand", "handedness_uncertain"),
        ("no_release", "release_unknown"),
        ("wide_release", "release_interval_wide"),
        ("no_release_arm", "release_context_missing"),
    ],
)
def test_teaching_quality_gates_explain_missing_comparison(change, reason):
    asset, track = fixture()
    if change == "unknown_hand":
        asset["analysis_config"]["handedness"] = "auto"
        asset["measurements"]["side_source"] = "ambiguous_estimate"
    elif change == "no_release":
        asset["phases"]["release"] = None
    elif change == "wide_release":
        asset["phases"]["release"]["range_us"] = [400000, 800000]
    else:
        for f in track["frames"]:
            if 400000 <= f["time_us"] <= 650000:
                f["landmarks"][14] = None
    result = build_pose_comparison(asset, track)
    assert result["comparison_status"] == "unavailable"
    assert result["reason"] == reason
    assert set(result["reason_text"]) == {"en", "zh"}
    assert result["available_frames"] == 0
    assert all(not any(f["target_landmarks"]) and not f["deltas"] for f in result["frames"])


def test_personal_reference_aligns_release_time_pixel_scale_and_translation():
    own, track = fixture()
    ref, ref_track = fixture("ref", shift_us=200000, pixel_scale=0.5, offset=(70, 20), width=700, height=600)
    result = build_pose_comparison(own, track, ref, ref_track, mode="reference")
    assert result["comparison_status"] == "conditional_personal_reference"
    assert result["source_type"] == "personal_reference_video"
    assert result["transformation"]["scale"] == pytest.approx(2)
    assert result["transformation"]["translation_px"] == pytest.approx([-140, -40])
    assert result["transformation"]["rotation_degrees"] == 0
    assert result["transformation"]["mirrored"] is False
    for output in result["frames"]:
        assert output["available"]
        assert output["reference_evidence"]["time_us"] - output["own_evidence"]["time_us"] == 200000
        assert output["alignment_error_us"] == 0
        own_points = track["frames"][output["frame_index"]]["landmarks"]
        for actual, target in zip(own_points, output["target_landmarks"]):
            if actual:
                assert target["x"] == pytest.approx(actual["x"])
                assert target["y"] == pytest.approx(actual["y"])
        assert all(d["value"] == pytest.approx(0) for d in output["deltas"])


def test_reference_uses_fixed_transform_preserving_later_drift_and_lean():
    own, track = fixture()
    ref, ref_track = fixture("ref")
    # Following release the reference leans/difts. Do not rotate/translate each
    # frame until it looks like own, which would erase the intended comparison.
    changed = ref_track["frames"][20]
    for p in changed["landmarks"]:
        if p:
            p["x"] += 0.05
    changed["landmarks"][12]["x"] += 0.03
    result = build_pose_comparison(own, track, ref, ref_track, mode="reference")
    target = result["frames"][20]["target_landmarks"]
    assert target[24]["x"] - track["frames"][20]["landmarks"][24]["x"] == pytest.approx(0.05)
    assert target[12]["x"] - track["frames"][20]["landmarks"][12]["x"] == pytest.approx(0.08)
    assert result["transformation"]["scale"] == pytest.approx(1)


@pytest.mark.parametrize(
    "condition,reason",
    [
        ("cross_view", "context_mismatch"),
        ("other_type", "context_mismatch"),
        ("unknown_view", "context_mismatch"),
        ("other_hand", "handedness_mismatch"),
        ("unverified_view", "view_unverified"),
        ("unknown_reference_hand", "reference_handedness_uncertain"),
        ("reference_no_release", "reference_release_unknown"),
    ],
)
def test_reference_cannot_produce_cross_view_or_mismatched_metrics(condition, reason):
    own, track = fixture()
    ref, refs = fixture("ref")
    if condition == "cross_view":
        ref["analysis_config"]["camera_view"] = "front"
    elif condition == "other_type":
        ref["analysis_config"]["shot_type"] = "stationary_jump_shot"
    elif condition == "unknown_view":
        ref["analysis_config"]["camera_view"] = "unknown"
    elif condition == "other_hand":
        ref["analysis_config"]["handedness"] = "left"
    elif condition == "unverified_view":
        ref["upstream"] = {}
    elif condition == "unknown_reference_hand":
        ref["analysis_config"]["handedness"] = "auto"
        ref["measurements"]["side_source"] = "ambiguous_estimate"
    else:
        ref["phases"]["release"] = None
    result = build_pose_comparison(own, track, ref, refs, mode="reference")
    assert result["reason"] == reason
    assert result["available_frames"] == 0
    assert all(f["deltas"] == [] and not any(f["target_landmarks"]) for f in result["frames"])


def test_user_confirmed_view_allows_personal_registration_without_camera_group():
    own, track = fixture()
    ref, refs = fixture("ref")
    ref["upstream"] = {}
    result = build_pose_comparison(own, track, ref, refs, mode="reference", assume_same_view=True)
    assert result["comparison_status"] == "conditional_personal_reference"
    assert result["transformation"]["camera_basis"] == "user_confirmed_same_view"


def test_missing_reference_window_and_internal_gaps_are_never_clamped():
    own, track = fixture()
    ref, refs = fixture("ref")
    refs["frames"] = [
        f
        for f in refs["frames"]
        if 200000 <= f["time_us"] <= 1200000 and not 750000 <= f["time_us"] <= 1050000
    ]
    result = build_pose_comparison(own, track, ref, refs, mode="reference")
    for index in (0, 3, 17, 18, 19, 25, 30):
        assert result["frames"][index]["reason"] == "reference_context_missing"
        assert result["frames"][index]["deltas"] == []
    assert result["frames"][10]["available"]


def test_reference_missing_landmarks_never_creates_substitute_joints():
    own, track = fixture()
    ref, refs = fixture("ref")
    refs["frames"][12]["landmarks"][14] = None
    refs["frames"][13]["landmarks"] = None
    result = build_pose_comparison(own, track, ref, refs, mode="reference")
    partial = result["frames"][12]
    assert partial["available"]
    assert partial["target_landmarks"][14] is None
    assert [12, 14] not in partial["connections"]
    assert [14, 16] not in partial["connections"]
    assert partial["deltas"] == []
    assert result["frames"][13]["reason"] == "reference_pose_not_visible"


def test_empty_track_and_no_reference_have_actionable_reasons():
    own, track = fixture()
    assert build_pose_comparison(own, {"frames": []})["reason"] == "track_missing"
    assert build_pose_comparison(own, track, mode="reference")["reason"] == "select_reference"

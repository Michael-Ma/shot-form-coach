"""Synthetic body geometry only; no private videos or captured poses are checked in."""

import copy
import json

import pytest
from app.segmentation import (
    ANOMALY_LIMIT,
    MAX_GAP_US,
    TRACE_LIMIT,
    duplicate_geometry,
    evaluate_samples,
    pose_geometry,
    propose_candidates,
    sample_poses,
)


def pose(*, x=0.5, raised=-0.4, quality=0.99):
    points = [{"x": x, "y": 0.5, "visibility": quality, "presence": quality} for _ in range(33)]
    positions = {
        0: (x, 0.30),
        11: (x - 0.06, 0.40),
        12: (x + 0.06, 0.40),
        23: (x - 0.05, 0.65),
        24: (x + 0.05, 0.65),
        13: (x - 0.09, 0.48),
        14: (x + 0.09, 0.48),
        15: (x - 0.10, 0.40 - raised * 0.25),
        16: (x + 0.10, 0.40 - raised * 0.25),
        25: (x - 0.05, 0.80),
        26: (x + 0.05, 0.80),
        27: (x - 0.06, 0.94),
        28: (x + 0.06, 0.94),
    }
    for index, (px, py) in positions.items():
        points[index].update(x=px, y=py)
    return points


def sample(stamp, height=-0.4, *, x=0.5, poses=None):
    return sample_poses([pose(x=x, raised=height)] if poses is None else poses, 640, 360, stamp)


def codes(candidate):
    return {a["code"] for a in candidate["evidence"]["anomalies"]}


def test_duplicate_full_body_geometry_is_order_and_resolution_invariant():
    main = pose(raised=0.8)
    duplicate = pose(x=0.506, raised=0.8, quality=0.95)
    duplicate[15]["y"] += 0.10  # One uncertain wrist can differ; the rest of the body must agree.
    for width, height in [(640, 360), (1920, 1080)]:
        for variants in [[main, duplicate], [duplicate, main]]:
            row = sample_poses(variants, width, height, 200_000)
            assert row["people_detected"] == 2 and row["distinct_pose_count"] == 1
            assert row["selection"] == "duplicate_cluster"
            assert row["left"] == pytest.approx(0.8)
            assert row["duplicate_comparisons"][0]["match"]
            assert row["anomaly_codes"] == ["duplicate_pose_merged"]


def test_nearby_distinct_people_and_overlapping_torsos_with_conflicting_limbs_remain_ambiguous():
    main, neighbor = pose(), pose(x=0.53)
    assert sample(0, poses=[main, neighbor])["selection"] == "ambiguous_people"
    conflicting = copy.deepcopy(main)
    for index in (13, 14, 15, 16, 25, 26):
        conflicting[index]["x"] += 0.14
    # Centers/torso boxes overlap perfectly, but independent body joints disagree.
    row = sample(0, poses=[main, conflicting])
    assert row["distinct_pose_count"] == 2 and row["selected_pose_index"] is None
    assert row["duplicate_comparisons"][0]["support_close_fraction"] < 0.75


def test_complete_link_clustering_does_not_merge_similarity_chain():
    row = sample(0, poses=[pose(x=0.48), pose(x=0.492), pose(x=0.504)])
    assert row["pose_groups"] == [[0, 1], [2]]
    assert row["distinct_pose_count"] == 2


def test_unreliable_or_nonfinite_joints_cannot_prove_duplicate_or_identity():
    a, b = pose(), pose()
    for index in (0, 13, 14, 15, 16, 25):
        b[index]["visibility"] = 0.2
    b[27]["x"] = float("nan")
    result = duplicate_geometry(pose_geometry(a, 640, 360), pose_geometry(b, 640, 360))
    assert not result["match"] and result["shared_support"] < 4
    b[11]["visibility"] = 0.2
    assert pose_geometry(b, 640, 360) is None
    assert sample(0, poses=[a, b])["selection"] == "ambiguous_people"
    bad_wrist = pose()
    bad_wrist[15]["visibility"] = float("nan")
    row = sample(0, poses=[bad_wrist])
    assert row["left"] is None
    json.dumps(evaluate_samples([row], 1_000_000), allow_nan=False)


def test_low_high_across_short_missing_gap_requires_same_geometry():
    rows = [sample(0), sample(200_000, poses=[]), sample(400_000, 0.8), sample(600_000)]
    result = evaluate_samples(rows, 2_000_000)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["peak_us"] == 400_000
    assert {"pose_missing", "short_gap_bridged"} <= codes(candidate)
    assert candidate["evidence"]["quality"] == "uncertain_motion_proposal"
    replaced = [
        sample(0, x=0.3),
        sample(200_000, poses=[]),
        sample(400_000, 0.8, x=0.7),
        sample(600_000, x=0.7),
    ]
    assert propose_candidates(replaced, 2_000_000) == []


@pytest.mark.parametrize("end,expected", [(MAX_GAP_US, 1), (MAX_GAP_US + 1, 0)])
def test_gap_boundary_is_measured_from_last_usable_sample(end, expected):
    rows = [
        sample(0),
        sample(200_000, poses=[]),
        sample(400_000, poses=[]),
        sample(end, 0.8),
        sample(end + 200_000),
    ]
    assert len(propose_candidates(rows, 2_000_000)) == expected


def test_timestamp_jump_without_missing_rows_also_cannot_bridge_long_gap():
    assert propose_candidates([sample(0), sample(800_000, 0.8), sample(1_000_000)], 2_000_000) == []


def test_repeated_ambiguous_samples_do_not_refresh_gap_timeout_or_erase_qualified_peak():
    two = [pose(x=0.3), pose(x=0.7)]
    rows = [sample(0), sample(200_000, 0.8)] + [
        sample(t, poses=two) for t in (400_000, 600_000, 800_000, 1_000_000, 1_200_000)
    ]
    result = evaluate_samples(rows, 2_000_000)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["peak_us"] == 200_000
    assert candidate["evidence"]["decision"] == "preserved_on_gap_timeout"
    assert candidate["evidence"]["decision_time_us"] == 1_000_000
    assert {"ambiguous_people", "observation_gap_timeout"} <= codes(candidate)
    assert result["decision_trace"][4]["pending_peak_us"] == 200_000  # Exactly 600 ms is retained.
    assert result["decision_trace"][5]["pending_peak_us"] is None


def test_unqualified_low_cannot_connect_through_true_two_person_interval_or_new_person():
    two = [pose(x=0.3), pose(x=0.7)]
    rows = [sample(0)] + [sample(t, poses=two) for t in (200_000, 400_000, 600_000, 800_000)]
    rows += [sample(1_000_000, 0.8), sample(1_200_000)]
    assert propose_candidates(rows, 2_000_000) == []
    assert (
        propose_candidates([sample(0, x=0.3), sample(200_000, 0.8, x=0.7), sample(400_000, x=0.7)], 1_000_000)
        == []
    )


def test_identity_switch_preserves_old_qualified_peak_once_and_does_not_promote_new_person():
    rows = [
        sample(0, x=0.3),
        sample(200_000, 0.8, x=0.3),
        sample(400_000, 1.2, x=0.7),
        sample(600_000, 1.3, x=0.7),
    ]
    result = evaluate_samples(rows, 2_000_000)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["peak_us"] == 200_000
    assert candidate["evidence"]["decision"] == "preserved_on_identity_change"
    assert "identity_discontinuity" in codes(candidate)


def test_qualified_peak_survives_short_disappearance_at_eof_exactly_once():
    rows = [sample(0), sample(200_000, 0.8), sample(400_000, poses=[])]
    candidates = propose_candidates(rows, 600_000)
    assert len(candidates) == 1
    assert {"pose_missing", "incomplete_end_context"} <= codes(candidates[0])
    assert candidates[0]["evidence"]["decision"] == "preserved_at_eof"


def test_duplicate_anomaly_survives_peak_update_and_does_not_leak_to_next_candidate():
    duplicates = [pose(raised=1.0), pose(x=0.505, raised=1.0, quality=0.95)]
    rows = [
        sample(0),
        sample(200_000, 0.7),
        sample(400_000, poses=duplicates),
        sample(600_000, 1.2),
        sample(800_000),
    ]
    rows += [sample(t) for t in range(1_000_000, 3_000_001, 200_000)]
    rows += [sample(3_200_000, 0.9), sample(3_400_000)]
    candidates = propose_candidates(rows, 4_000_000)
    assert len(candidates) == 2 and candidates[0]["peak_us"] == 600_000
    assert "duplicate_pose_merged" in codes(candidates[0])
    assert codes(candidates[1]) == set()
    assert candidates[1]["evidence"]["quality"] == "motion_proposal"


def test_static_high_or_only_missing_data_cannot_create_candidates():
    assert propose_candidates([sample(t, 0.8) for t in range(0, 2_000_000, 200_000)], 2_000_000) == []
    assert propose_candidates([sample(t, poses=[]) for t in range(0, 2_000_000, 200_000)], 2_000_000) == []


def test_evidence_is_bounded_explicitly_and_late_trace_anomalies_remain_visible():
    rows = [sample(i * 200_000, poses=[]) for i in range(TRACE_LIMIT + 20)]
    result = evaluate_samples(rows, len(rows) * 200_000)
    assert len(result["decision_trace"]) == TRACE_LIMIT and result["decision_trace_truncated"]
    assert len(result["anomaly_events"]) == ANOMALY_LIMIT and result["anomaly_events_truncated"]
    assert result["anomaly_counts"]["pose_missing"] == len(rows)
    assert result["decision_trace"][ANOMALY_LIMIT + 1]["anomaly_codes"] == ["pose_missing"]


def test_long_video_proposals_are_not_silently_capped():
    rows = []
    for index in range(205):
        start = index * 3_000_000
        rows += [sample(start), sample(start + 200_000, 0.8), sample(start + 400_000)]
    assert len(propose_candidates(rows, 620_000_000)) == 205


def test_adjacent_jump_motion_is_allowed_but_same_translation_after_gap_is_not_assumed_identity():
    low = pose()
    jumping = pose(raised=0.8)
    # A 0.7 torso-length vertical move is possible during a jump in consecutive samples.
    for point in jumping:
        point["y"] -= 0.175
    consecutive = [sample(0, poses=[low]), sample(200_000, poses=[jumping]), sample(400_000, poses=[jumping])]
    result = evaluate_samples(consecutive, 1_000_000)
    assert len(result["candidates"]) == 1
    assert result["decision_trace"][1]["identity_gate"]["gate"] == "adjacent_observation"
    interrupted = [sample(0, poses=[low]), sample(200_000, poses=[]), sample(400_000, poses=[jumping])]
    result = evaluate_samples(interrupted, 1_000_000)
    assert result["candidates"] == []
    assert result["decision_trace"][2]["identity_gate"]["gate"] == "gap_reacquisition"
    assert not result["decision_trace"][2]["identity_gate"]["match"]


def test_unreliable_single_wrist_does_not_bridge_unqualified_low_into_phantom_rise():
    before = pose()
    missing_right = pose()
    missing_right[16]["visibility"] = 0.2
    right_high = pose()
    right_high[16]["y"] = 0.40 - 0.8 * 0.25
    rows = [
        sample(0, poses=[before]),
        sample(200_000, poses=[missing_right]),
        sample(400_000, poses=[right_high]),
        sample(600_000),
    ]
    assert propose_candidates(rows, 1_000_000) == []


def test_unreliable_wrist_does_not_delete_a_previously_qualified_peak():
    missing = pose()
    missing[15]["visibility"] = missing[16]["visibility"] = 0.2
    rows = [sample(0), sample(200_000, 0.8), sample(400_000, poses=[missing]), sample(600_000)]
    candidates = propose_candidates(rows, 1_000_000)
    assert len(candidates) == 1 and candidates[0]["peak_us"] == 200_000
    assert "wrist_unreliable" in codes(candidates[0])


def test_scan_worker_persists_duplicate_anomaly_and_source_timestamp(tmp_path, monkeypatch):
    from app import worker as worker_module
    from app.config import Settings
    from app.db import Repository
    from app.segmentation import METHOD

    duplicates = [pose(raised=0.9), pose(x=0.505, raised=0.9, quality=0.95)]
    evaluated = evaluate_samples([sample(0), sample(200_000, poses=duplicates), sample(400_000)], 1_000_000)
    candidates = evaluated.pop("candidates")
    scan_result = {"candidates": candidates, "scan_evidence": {"method": METHOD, **evaluated}}
    settings = Settings(tmp_path)
    settings.prepare()
    repo = Repository(settings.db_path)
    repo.put("video", {"id": "synthetic_video", "status": "ready", "candidates": []})
    job = repo.new_job("video_scan", {"video_id": "synthetic_video"})
    monkeypatch.setattr(worker_module, "scan_video", lambda *_: scan_result)
    worker_module.Worker(settings, repo).execute(job)
    saved = repo.get("video", "synthetic_video")
    assert saved["scan_status"] == "succeeded"
    assert saved["scan_evidence"]["method"] == METHOD
    assert saved["scan_evidence"]["anomaly_counts"]["duplicate_pose_merged"] == 1
    anomaly = saved["scan_evidence"]["decision_trace"][1]
    assert anomaly["time_us"] == 200_000
    assert anomaly["raw_pose_count"] == 2 and anomaly["distinct_pose_count"] == 1
    assert anomaly["anomaly_codes"] == ["duplicate_pose_merged"]
    assert saved["candidates"][0]["evidence"]["anomalies"][0]["code"] == "duplicate_pose_merged"

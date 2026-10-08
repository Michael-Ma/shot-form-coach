from copy import deepcopy

import pytest
from app.analysis import compare, measure
from app.coaching import build_review, validate_model_coaching


def frames(count=29, lower_at=None, gap_at=None, step_us=50000):
    result = []
    for i in range(count):
        stamp = i * step_us
        points = [{"x": 0.5, "y": 0.5, "visibility": 1} for _ in range(33)]
        points[0]["y"] = 0.2
        for shoulder, elbow, wrist, hip in [(11, 13, 15, 23), (12, 14, 16, 24)]:
            points[shoulder]["y"] = 0.4
            points[elbow] = {"x": 0.52, "y": 0.3, "visibility": 1}
            points[wrist]["y"] = 0.5 if lower_at is not None and stamp >= lower_at else 0.1
            points[hip]["y"] = 0.7
        result.append(
            {
                "time_us": stamp,
                "source_time_us": stamp + 1000000,
                "frame_id": f"f{i}",
                "width": 600,
                "height": 600,
                "landmarks": None if stamp == gap_at else points,
            }
        )
    return result


def asset(track=None, side_source="user_setting", interval=None):
    track = frames() if track is None else track
    phases = {
        "release": {"range_us": interval or [200000, 200000], "source": "user_corrected"},
        "loading_bottom": {"range_us": [50000, 50000]},
    }
    return {
        "id": "shot",
        "revision": 4,
        "phases": phases,
        "frame_index": track,
        "analysis_config": {"camera_view": "side", "shot_type": "set_shot"},
        "measurements": measure({"frames": track}, phases, "right", side_source),
    }


def metrics(shot):
    return {m["key"]: m for m in shot["measurements"]["measurements"]}


def bi(text):
    return {"en": text, "zh": "这球的可见动作"}


def model_issue(rubric_id="relaxed_finish", severity="low", confidence="medium"):
    return {
        "rubric_id": rubric_id,
        "severity": severity,
        "confidence": confidence,
        "title": bi("Review this motion"),
        "observation": bi("The hand visibly lowers after release."),
        "standard_gap": bi("Try a comfortable completed finish."),
        "why_it_matters": bi("It can make the practice easier to review."),
        "action": bi("Try comfortable close-range shots."),
        "drill": bi("Try 5 form shots."),
        "evidence_frame_ids": ["f4", "f5"],
        "source_ids": ["curry-mechanics"],
    }


def model_coaching(issues=None):
    return {
        "overall_summary": bi("The visible release can be reviewed in the cited frames."),
        "strengths": [],
        "issues": [model_issue()] if issues is None else issues,
    }


def test_visible_motion_becomes_human_metrics_without_fake_faults():
    shot = asset()
    result = build_review(shot)
    assert result["status"] == "reviewed"
    assert result["issues"] == []
    assert "score" not in result
    assert len(result["metrics"]) == 4
    human = {m["id"]: m for m in result["metrics"]}
    assert human["release_rhythm"]["display_value"]["en"] == "About 0.15 s"
    assert human["release_hand_position"]["display_value"]["zh"] == "高于面部"
    assert human["raised_finish"]["display_value"]["en"] == "At least 1.00 s"
    assert "不足以确定具体技术问题" in result["overall"]["summary"]["zh"]
    assert set(human["raised_finish"]["evidence_frame_ids"]) <= {f["frame_id"] for f in shot["frame_index"]}


def test_sustained_withdrawal_only_yields_optional_low_priority_practice():
    shot = asset(frames(lower_at=650000))
    result = build_review(shot)
    assert len(result["issues"]) == 1
    issue = result["issues"][0]
    assert issue["severity"] == issue["confidence"] == "low"
    assert issue["basis"] == "measurement"
    assert "未证实为技术错误" in issue["why_it_matters"]["zh"]
    assert "0.45" in issue["observation"]["en"]
    assert metrics(shot)["finish_above_shoulder_ms"]["value"] == 450


def test_gap_hiding_withdrawal_cannot_create_short_finish_fault():
    shot = asset(frames(lower_at=650000, gap_at=600000))
    hold = metrics(shot)["finish_above_shoulder_ms"]
    assert hold["lower_bound"] is True
    assert hold["value"] == 350
    assert build_review(shot)["issues"] == []
    assert all(shot["frame_index"][int(f[1:])]["time_us"] < 600000 for f in hold["evidence_frame_ids"])


def test_too_short_prefix_remains_unknown_instead_of_counting_after_gap():
    shot = asset(frames(lower_at=650000, gap_at=400000))
    assert metrics(shot)["finish_above_shoulder_ms"]["value"] is None
    assert build_review(shot)["issues"] == []


@pytest.mark.parametrize("kwargs", [{"side_source": "ambiguous_estimate"}, {"interval": [100000, 800000]}])
def test_uncertain_release_or_side_withholds_precise_review(kwargs):
    shot = asset(frames(lower_at=650000), **kwargs)
    result = build_review(shot)
    assert result["status"] == "limited"
    assert result["issues"] == []
    assert result["outcome"] == "limited_visibility"
    available = [m["id"] for m in result["metrics"] if m["status"] == "measured"]
    # The known release and hip timing do not need an identified shooting arm.
    assert available == (["release_rhythm"] if "side_source" in kwargs else [])


def test_unanalyzed_review_invites_analysis_without_claiming_good_form():
    result = build_review({"id": "new", "frame_index": []})
    assert result["status"] == "awaiting_analysis"
    assert result["strengths"] == result["issues"] == []


def test_censored_finish_durations_are_not_compared_as_exact_values():
    first, other = asset(frames(29)), asset(frames(21))
    other.update(id="reference")
    result = compare(first, first["measurements"], other, other["measurements"], True)
    assert "finish_above_shoulder_ms" not in [d["key"] for d in result["differences"]]


def test_model_references_are_validated_and_priority_is_capped():
    coaching = model_coaching(
        [model_issue("comfortable_release", "high", "high"), model_issue("relaxed_finish", "high", "high")]
    )
    validated = validate_model_coaching(coaching, ["f4", "f5"])
    assert validated["issues"][0]["severity"] == "medium"
    assert validated["issues"][1]["severity"] == "low"
    assert all(i["confidence"] == "medium" for i in validated["issues"])
    bad_frame = deepcopy(coaching)
    bad_frame["issues"][0]["evidence_frame_ids"] = ["never-supplied"]
    with pytest.raises(ValueError, match="frame evidence"):
        validate_model_coaching(bad_frame, ["f4", "f5"])
    bad_source = deepcopy(coaching)
    bad_source["issues"][0]["source_ids"] = ["invented-science"]
    with pytest.raises(ValueError, match="source evidence"):
        validate_model_coaching(bad_source, ["f4", "f5"])


def test_model_cannot_invent_measurements_or_claim_habit_from_one_shot():
    coaching = model_coaching()
    coaching["issues"][0]["observation"] = bi("Your elbow is at 90 degrees.")
    with pytest.raises(ValueError, match="measurement numbers"):
        validate_model_coaching(coaching, ["f4", "f5"])
    coaching["issues"][0]["observation"] = bi("You consistently push with the guide hand.")
    with pytest.raises(ValueError, match="habitual technique"):
        validate_model_coaching(coaching, ["f4", "f5"])


def test_stale_model_evaluation_does_not_survive_phase_revision():
    shot = asset()
    shot["model_assist"] = {"asset_revision": 3, "coaching": model_coaching()}
    assert build_review(shot)["issues"] == []
    shot["model_assist"]["asset_revision"] = 4
    assert build_review(shot)["issues"][0]["basis"] == "model"


def test_model_does_not_override_uncertain_phase_gate():
    shot = asset(interval=[100000, 800000])
    shot["model_assist"] = {"asset_revision": 4, "coaching": model_coaching()}
    result = build_review(shot)
    assert result["issues"] == []
    assert result["status"] == "limited"


def test_reference_difference_alone_is_not_a_form_fault():
    result = build_review(
        asset(),
        {
            "status": "conditional_projection_comparison",
            "differences": [{"key": "arm_lowering", "difference": 1.8}],
        },
    )
    assert result["issues"] == []
    assert any("不是已验证的标准动作" in limit["zh"] for limit in result["limitations"])


@pytest.mark.parametrize("fps", [20, 30, 60, 120])
def test_sustained_withdrawal_is_detected_at_every_supported_frame_rate(fps):
    shot = asset(frames(count=2 * fps, lower_at=650000, step_us=round(1000000 / fps)))
    hold = metrics(shot)["finish_above_shoulder_ms"]
    assert hold["crossed_shoulder"] is True
    assert hold["lower_bound"] is False
    assert abs(hold["value"] - 450) <= 1000 / fps + 1
    result = build_review(shot)
    assert len(result["issues"]) == 1
    assert result["strengths"] == []


def test_near_shoulder_ambiguity_cannot_claim_a_long_raised_finish():
    track = frames()
    for frame in track:
        if frame["time_us"] >= 400000:
            frame["landmarks"][16]["y"] = 0.403
    shot = asset(track)
    assert metrics(shot)["finish_above_shoulder_ms"]["value"] is None
    assert build_review(shot)["strengths"] == []


def test_intermittent_lowering_does_not_count_as_continuously_raised():
    track = frames()
    track[12]["landmarks"][16]["y"] = 0.5
    shot = asset(track)
    hold = metrics(shot)["finish_above_shoulder_ms"]
    assert hold["lower_bound"] is True
    assert hold["value"] == 350
    assert "f12" not in hold["evidence_frame_ids"]


def test_lower_bound_starts_at_latest_possible_release():
    shot = asset(interval=[100000, 250000])
    # End the clip at 1.1s. Counting from midpoint would overclaim 925ms.
    shot = asset(frames(count=23), interval=[100000, 250000])
    hold = metrics(shot)["finish_above_shoulder_ms"]
    assert hold["lower_bound"] is True
    assert hold["value"] == 850


def test_unknown_shot_context_does_not_create_local_technique_suggestion():
    shot = asset(frames(lower_at=650000))
    shot["analysis_config"]["shot_type"] = "unknown"
    assert build_review(shot)["issues"] == []


def test_temporal_model_claim_needs_multiple_distinct_frames():
    coaching = model_coaching()
    coaching["issues"][0]["evidence_frame_ids"] = ["f4", "f4"]
    with pytest.raises(ValueError, match="multiple distinct frames"):
        validate_model_coaching(coaching, ["f4", "f5"])


def test_model_cannot_redefine_the_standard_or_add_unevidenced_summary():
    coaching = model_coaching()
    coaching["issues"][0]["standard_gap"] = bi("Lock the elbow rigidly on every shot.")
    validated = validate_model_coaching(coaching, ["f4", "f5"])
    assert "required hold time" in validated["issues"][0]["standard_gap"]["en"]
    shot = asset()
    shot["model_assist"] = {"asset_revision": 4, "coaching": model_coaching([])}
    result = build_review(shot)
    assert "Dip to release" in result["overall"]["summary"]["en"]


def reviewed_without_faults():
    """Shape of the accepted existing reviews: cited strengths, no invented faults."""
    return {
        "overall_summary": {
            "en": "The visible rise connects into extension and the landing stays controlled. The guide hand is too small to assess precisely.",
            "zh": "可见起身连贯地接入伸展，落地保持可控。辅助手画面太小，无法精细判断。",
        },
        "strengths": [
            {
                "title": bi(title),
                "detail": bi(detail),
                "evidence_frame_ids": ["f4", "f5"],
            }
            for title, detail in [
                ("Connected rise", "The visible body rise connects into the arm motion."),
                ("Completed extension", "The arm visibly continues through the release."),
                ("Controlled landing", "The feet settle without a visible recovery step."),
            ]
        ],
        "issues": [],
    }


@pytest.mark.parametrize("side_source", ["user_setting", "ambiguous_estimate"])
def test_cited_model_strengths_without_issues_are_a_completed_visual_review(side_source):
    shot = asset(side_source=side_source)
    coaching = reviewed_without_faults()
    shot["model_assist"] = {"asset_revision": 4, "coaching": coaching}
    result = build_review(shot)
    assert result["outcome"] == "no_priority_issue"
    assert result["assessment_source"] == "model"
    assert result["overall"]["summary"] == coaching["overall_summary"]
    assert result["strengths"] == coaching["strengths"]
    assert result["issues"] == []
    assert "不代表动作完美" in result["empty_state"]["detail"]["zh"]
    assert result["coverage"]["model_review"] == "accepted"
    assert result["coverage"]["dimension_coverage"] == "unspecified"
    assert result["coverage"]["dimensions"] == []
    if side_source == "ambiguous_estimate":
        assert any("出手侧" in item["zh"] for item in result["limitations"])
        assert result["coverage"]["available_metrics"] == 1


def test_failed_visual_call_is_not_reported_as_poor_video_visibility():
    shot = asset()
    shot.update(model_assist=None, model_error="GeminiClientError")
    result = build_review(shot)
    assert result["outcome"] == "model_failed"
    assert result["coverage"]["model_review"] == "failed"
    assert result["coverage"]["available_metrics"] == 4
    assert "处理失败" in result["empty_state"]["detail"]["zh"]
    assert result["overall"]["headline"]["zh"] == "本次视觉评价未完成"


def test_local_measurements_do_not_claim_a_clean_visual_assessment():
    result = build_review(asset())
    assert result["outcome"] == "measurements_only"
    assert result["coverage"]["model_review"] == "not_run"
    assert result["empty_state"]["title"]["zh"] == "动作数据已就绪"
    new = build_review({"id": "new", "frame_index": []})
    assert new["outcome"] == "awaiting_analysis"


@pytest.mark.parametrize("kwargs", [{"side_source": "ambiguous_estimate"}, {"interval": [100000, 800000]}])
def test_local_uncertainty_withholds_only_dependent_model_issues(kwargs):
    shot = asset(**kwargs)
    coaching = reviewed_without_faults()
    coaching["issues"] = [model_issue("comfortable_release"), model_issue("balanced_landing")]
    shot["model_assist"] = {"asset_revision": 4, "coaching": coaching}
    result = build_review(shot)
    assert result["assessment_source"] == "model"
    assert result["outcome"] == "issues_found"
    assert [item["rubric_id"] for item in result["issues"]] == ["balanced_landing"]
    assert result["coverage"]["withheld_dimensions"] == ["comfortable_release"]
    assert result["strengths"] == coaching["strengths"]
    assert result["overall"]["summary"] == coaching["overall_summary"]


def test_withheld_model_issue_does_not_become_no_priority_issue():
    shot = asset(interval=[100000, 800000])
    shot["model_assist"] = {"asset_revision": 4, "coaching": model_coaching()}
    result = build_review(shot)
    assert result["assessment_source"] == "model"
    assert result["outcome"] == "limited_visibility"
    assert result["issues"] == []
    assert result["coverage"]["withheld_dimensions"] == ["relaxed_finish"]


def test_stale_no_fault_review_does_not_claim_current_shot_is_clear():
    shot = asset()
    shot["model_assist"] = {"asset_revision": 3, "coaching": reviewed_without_faults()}
    result = build_review(shot)
    assert result["outcome"] == "measurements_only"
    assert result["assessment_source"] == "measurements"
    assert result["coverage"]["model_review"] == "stale"
    assert result["overall"]["summary"] != shot["model_assist"]["coaching"]["overall_summary"]


def test_coverage_distinguishes_observed_alignment_from_unseen_details():
    shot = asset()
    coaching = model_coaching([])
    coaching["coverage"] = [
        {
            "rubric_id": "balanced_landing",
            "status": "aligned",
            "detail": bi("The visible landing is controlled."),
            "evidence_frame_ids": ["f4", "f5"],
        },
        {
            "rubric_id": "quiet_guide_hand",
            "status": "not_visible",
            "detail": bi("The hands cannot be separated in this view."),
            "evidence_frame_ids": [],
        },
    ]
    shot["model_assist"] = {"asset_revision": 4, "coaching": coaching}
    result = build_review(shot)
    assert result["outcome"] == "no_priority_issue"
    assert result["coverage"]["dimension_coverage"] == "reported"
    assert result["coverage"]["dimensions"] == coaching["coverage"]
    coaching["coverage"][0]["status"] = "uncertain"
    assert build_review(shot)["outcome"] == "limited_visibility"


def test_coverage_requires_valid_evidence_for_assessed_dimensions():
    coaching = model_coaching([])
    dimension = {
        "rubric_id": "balanced_landing",
        "status": "aligned",
        "detail": bi("The landing is controlled in this view."),
        "evidence_frame_ids": [],
    }
    coaching["coverage"] = [dimension]
    with pytest.raises(ValueError, match="requires frame evidence"):
        validate_model_coaching(coaching, ["f4", "f5"])
    dimension["evidence_frame_ids"] = ["f4", "f4"]
    with pytest.raises(ValueError, match="multiple distinct frames"):
        validate_model_coaching(coaching, ["f4", "f5"])
    dimension["evidence_frame_ids"] = ["f4", "unseen"]
    with pytest.raises(ValueError, match="frame evidence"):
        validate_model_coaching(coaching, ["f4", "f5"])
    dimension["evidence_frame_ids"] = ["f4", "f5"]
    validate_model_coaching(coaching, ["f4", "f5"])
    coaching["coverage"].append(deepcopy(dimension))
    with pytest.raises(ValueError, match="duplicate coaching coverage"):
        validate_model_coaching(coaching, ["f4", "f5"])

"""Human-readable shooting review with evidence-bounded, provisional coaching.

Measurements describe one visible attempt. The rubric supplies qualitative teaching
principles; it is not a validated classifier or a universal ideal-pose template.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Bilingual(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str = Field(min_length=1, max_length=1800)
    zh: str = Field(min_length=1, max_length=1800)


class ModelStrength(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Bilingual
    detail: Bilingual
    evidence_frame_ids: list[str] = Field(min_length=1, max_length=30)


RubricId = Literal[
    "coordinated_rise", "balanced_landing", "comfortable_release", "quiet_guide_hand", "relaxed_finish"
]


class ModelIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_id: RubricId
    severity: Literal["high", "medium", "low"]
    confidence: Literal["high", "medium", "low"]
    title: Bilingual
    observation: Bilingual
    standard_gap: Bilingual
    why_it_matters: Bilingual
    action: Bilingual
    drill: Bilingual
    evidence_frame_ids: list[str] = Field(min_length=1, max_length=30)
    source_ids: list[str] = Field(min_length=1, max_length=5)


class ModelCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_id: RubricId
    status: Literal["aligned", "needs_review", "not_visible", "uncertain"]
    detail: Bilingual
    evidence_frame_ids: list[str] = Field(max_length=30)


class ModelCoaching(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_summary: Bilingual
    strengths: list[ModelStrength] = Field(max_length=3)
    issues: list[ModelIssue] = Field(max_length=3)
    # Older cached reviews lack coverage; accepting them must not imply that all
    # dimensions were assessed or that unseen hands were judged to be correct.
    coverage: list[ModelCoverage] = Field(default_factory=list, max_length=5)


def bi(en, zh):
    return {"en": en, "zh": zh}


@lru_cache(maxsize=1)
def load_rubric():
    return json.loads((Path(__file__).resolve().parents[2] / "references/coaching-rubric.json").read_text())


def validate_model_coaching(coaching, frame_ids):
    """Validate provenance before accepting prose; cap unverified issue priority.

    Frame references prove what inputs were available, not that every interpretation
    is correct. High-severity diagnoses require a future coach-confirmed workflow.
    """
    parsed = coaching if isinstance(coaching, ModelCoaching) else ModelCoaching.model_validate(coaching)
    result = parsed.model_dump(mode="json")
    supplied = set(frame_ids)
    rubric = {r["id"]: r for r in load_rubric()["dimensions"]}
    for issue in result["issues"]:
        # The model describes the observed event; it cannot redefine the standard.
        issue["standard_gap"] = rubric[issue["rubric_id"]]["teaching_goal"]
    seen = set()
    assertions = [result["overall_summary"]]
    assertions.extend(item[field] for item in result["strengths"] for field in ("title", "detail"))
    assertions.extend(
        item[field]
        for item in result["issues"]
        for field in ("title", "observation", "standard_gap", "why_it_matters")
    )
    assertions.extend(item["detail"] for item in result["coverage"])
    # Models may propose repetition counts in actions/drills, but measurement
    # numbers belong to the program's cards and cannot be silently invented here.
    frame_numbers = {
        int(match.group(1)) for frame_id in supplied if (match := re.search(r"(?:frame:|^f)(\d+)$", frame_id))
    }
    for assertion in assertions:
        for text in assertion.values():

            def checked_frame_reference(match):
                if int(match.group(1)) not in frame_numbers:
                    raise ValueError("invalid narrative frame evidence")
                return "referenced frame"

            numeric_claims = re.sub(r"(?i)\bframe\s+(\d+)\b", checked_frame_reference, text)
            numeric_claims = re.sub(r"第\s*(\d+)\s*帧", checked_frame_reference, numeric_claims)
            if re.search(r"\d|[一二三四五六七八九十百]\s*(秒|度|厘米|毫米|百分)", numeric_claims):
                raise ValueError("model coaching must not assert measurement numbers")
            if re.search(
                r"\b(consistently|always|habitual|every shot)\b|习惯性|总是|每一球|一贯",
                text,
                flags=re.IGNORECASE,
            ):
                raise ValueError("one shot cannot establish habitual technique")
    for item in result["strengths"] + result["issues"]:
        if not item["evidence_frame_ids"] or not set(item["evidence_frame_ids"]) <= supplied:
            raise ValueError("invalid coaching frame evidence")
    for issue in result["issues"]:
        if issue["rubric_id"] in seen:
            raise ValueError("duplicate coaching dimension")
        seen.add(issue["rubric_id"])
        if (
            issue["rubric_id"] in ("coordinated_rise", "balanced_landing", "relaxed_finish")
            and len(set(issue["evidence_frame_ids"])) < 2
        ):
            raise ValueError("temporal coaching requires multiple distinct frames")
        standard = rubric[issue["rubric_id"]]
        if not set(issue["source_ids"]) <= set(standard["source_ids"]):
            raise ValueError("invalid coaching source evidence")
        issue["severity"] = (
            "low"
            if issue["rubric_id"] == "relaxed_finish"
            else ("medium" if issue["severity"] == "high" else issue["severity"])
        )
        if issue["confidence"] == "high":
            issue["confidence"] = "medium"
    covered = set()
    for item in result["coverage"]:
        if item["rubric_id"] in covered:
            raise ValueError("duplicate coaching coverage dimension")
        covered.add(item["rubric_id"])
        evidence = set(item["evidence_frame_ids"])
        if not evidence <= supplied:
            raise ValueError("invalid coverage frame evidence")
        if item["status"] in ("aligned", "needs_review"):
            if not evidence:
                raise ValueError("assessed coverage requires frame evidence")
            if (
                item["rubric_id"] in ("coordinated_rise", "balanced_landing", "relaxed_finish")
                and len(evidence) < 2
            ):
                raise ValueError("temporal coverage requires multiple distinct frames")
    return result


def _metric(key, label, display, interpretation, source=None):
    source = source or {}
    return {
        "id": key,
        "label": label,
        "display_value": display,
        "interpretation": interpretation,
        "status": "measured" if source.get("value") is not None else "unavailable",
        "evidence_frame_ids": source.get("evidence_frame_ids", []),
    }


def _unavailable(key, label, interpretation):
    return _metric(key, label, bi("Not clear enough", "暂时看不清"), interpretation)


def _finite_measurements(asset):
    import math

    result = {}
    for m in (asset.get("measurements") or {}).get("measurements", []):
        value = m.get("value")
        if isinstance(value, (int, float)) and math.isfinite(value):
            result[m["key"]] = m
    return result


def _measurement_limits(asset):
    measures = asset.get("measurements") or {}
    release = (asset.get("phases") or {}).get("release")
    phase_uncertain = (
        "release_unknown" in measures.get("flags", [])
        or not release
        or release["range_us"][1] - release["range_us"][0] > 150000
    )
    side_uncertain = measures.get("side_source") == "ambiguous_estimate"
    return bool(phase_uncertain), side_uncertain


def _human_metrics(asset):
    values = _finite_measurements(asset)
    phase_uncertain, side_uncertain = _measurement_limits(asset)
    if phase_uncertain:
        values = {}
    elif side_uncertain:
        # Hip timing does not depend on which arm shoots. Uncertain arm tracking
        # must not remove an independently identified, narrow release interval.
        values = {key: value for key, value in values.items() if key == "loading_to_release"}
    metrics = []
    rhythm = values.get("loading_to_release")
    if rhythm:
        seconds = rhythm["value"] / 1000
        metrics.append(
            _metric(
                "release_rhythm",
                bi("Dip to release", "下沉到出手"),
                bi(f"About {seconds:.2f} s", f"约 {seconds:.2f} 秒"),
                bi(
                    "Estimated from the lowest visible hip position to release. Use repeated shots to review rhythm; faster is not automatically better.",
                    "从画面中髋部最低点算到离手，反映这球的起身阶段时长。对比多球看节奏，不以越快越好。",
                ),
                rhythm,
            )
        )
    else:
        metrics.append(
            _unavailable(
                "release_rhythm",
                bi("Dip to release", "下沉到出手"),
                bi(
                    "A clear dip and release are needed to estimate this phase.",
                    "需要看清下沉过程和离手时刻，才能估计这段动作时长。",
                ),
            )
        )
    face, shoulder = values.get("release_wrist_above_face"), values.get("release_wrist_height")
    if face:
        height = face["value"]
        display = (
            bi("Above face level", "高于面部")
            if height > 0.05
            else (
                bi("Below face level", "低于面部") if height < -0.05 else bi("Around face level", "面部附近")
            )
        )
        metrics.append(
            _metric(
                "release_hand_position",
                bi("Hand at release", "出手时手的位置"),
                display,
                bi(
                    "Shooting-wrist position near release, as seen by this camera. This is not ball release height or an ideal height target.",
                    "观察离手附近出手侧手腕相对面部的位置；这是画面中的手位，不能当作球的实际出手高度或统一达标线。",
                ),
                face,
            )
        )
    elif shoulder:
        display = (
            bi("Above shoulder level", "高于肩部")
            if shoulder["value"] > 0.05
            else (
                bi("Below shoulder level", "低于肩部")
                if shoulder["value"] < -0.05
                else bi("Around shoulder level", "肩部附近")
            )
        )
        metrics.append(
            _metric(
                "release_hand_position",
                bi("Hand at release", "出手时手的位置"),
                display,
                bi(
                    "The face is unclear, so this uses the shoulder as the visible reference. Hand position alone does not establish a fault.",
                    "面部关键点不够清楚，因此用肩部作参照。单看这个手位不能判定动作对错。",
                ),
                shoulder,
            )
        )
    else:
        metrics.append(
            _unavailable(
                "release_hand_position",
                bi("Hand at release", "出手时手的位置"),
                bi(
                    "A clearer release moment and visible shooting arm are needed.",
                    "需要更清楚的离手时刻和出手侧手臂。",
                ),
            )
        )
    hold = values.get("finish_above_shoulder_ms")
    if hold:
        seconds = hold["value"] / 1000
        display = (
            bi(f"At least {seconds:.2f} s", f"至少 {seconds:.2f} 秒")
            if hold.get("lower_bound")
            else (bi(f"About {seconds:.2f} s", f"约 {seconds:.2f} 秒"))
        )
        detail = (
            bi(
                "The shooting hand stayed above shoulder level through the clear observation window. This records the visible finish, not a required hold time.",
                "在连续看清的这段画面内，出手手腕一直高于肩部。这是收势的观察记录，没有规定必须保持几秒。",
            )
            if hold.get("lower_bound")
            else (
                bi(
                    "Time from release until the hand is clearly below shoulder level. This does not explain why a shot missed.",
                    "从离手到手腕持续降至肩部以下的时间，帮助观察收势；不能据此解释为什么没投进。",
                )
            )
        )
        metrics.append(
            _metric("raised_finish", bi("Raised-hand finish", "出手后抬手保持"), display, detail, hold)
        )
    else:
        metrics.append(
            _unavailable(
                "raised_finish",
                bi("Raised-hand finish", "出手后抬手保持"),
                bi(
                    "Keep the shooting arm in view after release to observe the finish.",
                    "出手后继续保留手臂画面，才能连续观察收势。",
                ),
            )
        )
    drop = values.get("arm_lowering")
    if drop:
        amount = abs(drop["value"] * 100)
        verb_en, verb_zh = ("Lowered", "降低") if drop["value"] >= 0 else ("Rose", "升高")
        metrics.append(
            _metric(
                "finish_movement",
                bi("Hand movement after release", "随挥手位变化"),
                bi(f"{verb_en} ~{amount:.0f}% of torso length", f"{verb_zh}约 {amount:.0f}% 躯干长度"),
                bi(
                    "Compares shoulder-relative wrist height around 0.2 s and 0.7 s after release. Camera angle and body rotation affect it; there is no ideal percentage.",
                    "比较离手后约 0.2 秒与 0.7 秒时，手腕相对肩部的位置。用肩到髋的画面长度作尺度；视角和转身会影响数值，没有统一理想百分比。",
                ),
                drop,
            )
        )
    else:
        metrics.append(
            _unavailable(
                "finish_movement",
                bi("Hand movement after release", "随挥手位变化"),
                bi(
                    "Needs a clear arm and enough footage after release.",
                    "需要出手后足够长、能看清手臂的画面。",
                ),
            )
        )
    return metrics, values, phase_uncertain or side_uncertain


def _local_finish_issue(asset, values):
    if asset.get("analysis_config", {}).get("shot_type") not in ("stationary_jump_shot", "set_shot"):
        return None
    hold = values.get("finish_above_shoulder_ms")
    # 600 ms is an observation-selection gate for optional practice, never a
    # validated minimum follow-through time or a pass/fail boundary.
    if not hold or not hold.get("crossed_shoulder") or hold["value"] > 600:
        return None
    standard = next(d for d in load_rubric()["dimensions"] if d["id"] == "relaxed_finish")
    seconds = hold["value"] / 1000
    return {
        "id": "local_relaxed_finish",
        "rubric_id": "relaxed_finish",
        "rank": 1,
        "severity": "low",
        "confidence": "low",
        "basis": "measurement",
        "title": bi("Try keeping a relaxed finish", "可以试着把随挥留住"),
        "observation": bi(
            f"The shooting hand is raised just after release, then is clearly below the shoulder about {seconds:.2f} s later.",
            f"这球离手后手臂先抬起，约 {seconds:.2f} 秒后，手腕已持续降至肩部以下。",
        ),
        "standard_gap": standard["teaching_goal"],
        "why_it_matters": bi(
            "A briefly retained, relaxed finish can make close-range form practice easier to review. This is an optional practice cue, not an established fault or a cause of a miss.",
            "近距离练习时稍留放松的收势，便于观察每球离手附近的动作。这是一项可尝试的练习提示，并未证实为技术错误，也不能解释未命中原因。",
        ),
        "action": bi(
            "On the next few comfortable close-range shots, complete the motion and briefly leave the shooting hand relaxed in its finish.",
            "下一组舒适距离的近投中，完整做完动作，轻松地把出手手臂留在收势位置片刻。",
        ),
        "drill": standard["suggested_drill"],
        "evidence_frame_ids": hold["evidence_frame_ids"],
        "source_ids": standard["source_ids"],
    }


def _next_practice(issues, limited=False):
    if issues:
        first = issues[0]
        standard = next(d for d in load_rubric()["dimensions"] if d["id"] == first["rubric_id"])
        return {
            "title": bi("Next set: focus on one change", "下一组，只练一个重点"),
            "instruction": first["drill"],
            "success_check": standard["practice_check"],
        }
    if limited:
        return {
            "title": bi("Get a clearer review of your next set", "先把下一组拍清楚"),
            "instruction": bi(
                "Record five comfortable close-range shots from one fixed angle, keeping the full body and ball visible before and after release. Confirm the shooting hand and release moment.",
                "固定同一机位拍 5 次舒适距离的近投，出手前后都保留全身和球；确认出手手和离手时刻。",
            ),
            "success_check": bi(
                "Check that the dip, release and landing stay in frame. Then compare shots with the same conditions.",
                "回看时能连续看到下沉、离手和落地，再比较同条件的几球。",
            ),
        }
    return {
        "title": bi("Next set: check your own repeatability", "下一组，找自己的稳定动作"),
        "instruction": bi(
            "Shoot five comfortable close-range attempts from the same spot. Keep one natural rhythm, record makes and misses, and review the release and finish together.",
            "在同一位置做 5 次舒适距离的近投，保持自然节奏，记录进球与否，再一起回看每球的出手与收势。",
        ),
        "success_check": bi(
            "Look for a motion you can repeat comfortably across the set. A single shot or a closer match to another player cannot establish better technique.",
            "找出这组里能舒适重复的动作。需要多球验证，单球或更像别人都不能证明技术更好。",
        ),
    }


def _empty_state(outcome):
    states = {
        "issues_found": (
            bi("Start with the first practice priority", "先从第一个练习重点开始"),
            bi(
                "Review the cited moment and try one change in the next set.",
                "回看对应画面，下一组只尝试一个调整。",
            ),
        ),
        "no_priority_issue": (
            bi("No major visible fault identified", "这球未发现明显的优先问题"),
            bi(
                "The visual review found supported strengths without a clear correction to prioritize in this attempt. This does not establish perfect form or rule out details that were not visible.",
                "视觉评价记录了有画面支持的优点，这一球中没有发现需要优先纠正的明确问题。这不代表动作完美，也不代表看不清的细节已经达标。",
            ),
        ),
        "limited_visibility": (
            bi("Some details still need a clearer view", "部分动作还需要看清"),
            bi(
                "The available evidence is insufficient for the remaining judgments. Keep the supported observations and check the listed visibility or timing limits before choosing a correction.",
                "剩余判断缺少足够证据。先保留已有依据的动作观察，再查看哪些细节受视角、出手侧或离手时刻影响，不把看不清当作技术错误。",
            ),
        ),
        "model_failed": (
            bi("Visual review did not complete", "本次视觉评价未完成"),
            bi(
                "The selected model call or response validation failed. Available local motion measurements are retained; this is a processing failure, not a judgment of your shooting or video quality.",
                "所选模型调用或结果校验失败，已有本地动作数据仍然保留。这是处理失败，不是对投篮水平或视频清晰度的判断。",
            ),
        ),
        "measurements_only": (
            bi("Motion measurements are ready", "动作数据已就绪"),
            bi(
                "This review currently contains local motion measurements. Choose a visual model and analyze the shot for an evidence-linked assessment of coordination, landing and hand action.",
                "当前结果主要来自本地动作测量。选择视觉模型并分析这一球，可进一步评价起身衔接、落地和手部动作，并回看对应证据。",
            ),
        ),
        "awaiting_analysis": (
            bi("Analyze this shot to start your review", "先分析这一球"),
            bi(
                "Run an analysis to see the visible movement, available measurements and supported practice priorities.",
                "分析后即可查看动作观察、可用数据和有证据支持的练习重点。",
            ),
        ),
    }
    title, detail = states[outcome]
    return {"title": title, "detail": detail}


def build_review(asset, comparison=None):
    rubric = load_rubric()
    has_analysis = bool(asset.get("measurements"))
    metrics, values, phase_limited = _human_metrics(asset)
    issues, strengths = [], []
    limitations = [
        bi(
            "These measurements describe one camera view and one attempt. Teaching principles guide review; they do not define a universal ideal pose.",
            "这些数据描述一个机位下的一次投篮。教学原则帮助复盘，不代表所有人都该采用同一个姿势。",
        )
    ]
    model = asset.get("model_assist") or {}
    coaching = None
    model_failed = bool(asset.get("model_error"))
    model_stale = bool(model.get("coaching") and model.get("asset_revision") != asset.get("revision"))
    if model.get("coaching") and not model_stale:
        try:
            coaching = validate_model_coaching(
                model["coaching"], [f["frame_id"] for f in asset.get("frame_index", [])]
            )
        except (ValueError, TypeError):
            model_failed = True
            limitations.append(
                bi(
                    "The visual review could not be linked to valid evidence, so it was not used.",
                    "视觉评价未能关联到有效证据，因此未纳入本次结论。",
                )
            )
    phase_uncertain, side_uncertain = _measurement_limits(asset)
    withheld_dimensions = []
    if coaching:
        strengths = coaching["strengths"][:3]
        for item in coaching["issues"]:
            # Landing and whole-body sequence observations do not depend on the
            # local tracker's arm choice or exact release anchor. Keep them and
            # cited visual strengths, while withholding judgments whose rubric
            # explicitly needs hand identity or clear separation.
            if (phase_uncertain or side_uncertain) and item["rubric_id"] in (
                "comfortable_release",
                "quiet_guide_hand",
                "relaxed_finish",
            ):
                withheld_dimensions.append(item["rubric_id"])
                continue
            issues.append({**item, "id": "visual_" + item["rubric_id"], "rank": 0, "basis": "model"})
        limitations.append(
            bi(
                "Visual coaching suggestions still need confirmation in the cited frames and repeated practice; severity is review priority, not a validated diagnosis.",
                "视觉教练建议仍需结合所引画面和重复练习确认；问题等级表示复盘优先级，并非经过验证的技术诊断。",
            )
        )
    local = _local_finish_issue(asset, values)
    if local and not any(i["rubric_id"] == "relaxed_finish" for i in issues):
        issues.append(local)
    severity_order, confidence_order = {"high": 0, "medium": 1, "low": 2}, {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (severity_order[i["severity"]], confidence_order[i["confidence"]]))
    issues = [{**issue, "rank": rank} for rank, issue in enumerate(issues[:3], 1)]
    hold = values.get("finish_above_shoulder_ms")
    if (
        not strengths
        and hold
        and hold.get("lower_bound")
        and not any(i["rubric_id"] == "relaxed_finish" for i in issues)
    ):
        seconds = hold["value"] / 1000
        strengths.append(
            {
                "title": bi("You retained a raised-hand finish", "出手后保留了抬手收势"),
                "detail": bi(
                    f"The shooting hand remains above the shoulder for at least {seconds:.2f} s of clear footage. You can use this as a personal reference in the next set.",
                    f"连续看清的画面中，手腕在离手后至少 {seconds:.2f} 秒仍高于肩部。下一组可以保留这个动作作个人参照。",
                ),
                "evidence_frame_ids": hold["evidence_frame_ids"],
            }
        )
    available = [m for m in metrics if m["status"] == "measured"]
    limited = phase_limited or len(available) < 2
    if model_failed and not coaching:
        outcome = "model_failed"
    elif not has_analysis and not coaching:
        outcome = "awaiting_analysis"
    elif issues:
        outcome = "issues_found"
    elif (
        coaching
        and not withheld_dimensions
        and (coaching["strengths"] or any(item["status"] == "aligned" for item in coaching["coverage"]))
        and not any(item["status"] == "needs_review" for item in coaching["coverage"])
    ):
        outcome = "no_priority_issue"
    elif coaching or limited:
        outcome = "limited_visibility"
    else:
        outcome = "measurements_only"
    empty_state = _empty_state(outcome)
    descriptions_en, descriptions_zh = [], []
    by_id = {m["id"]: m for m in available}
    for key, intro_en, intro_zh in [
        ("release_rhythm", "Dip to release: ", "这球下沉到出手"),
        ("release_hand_position", "Shooting hand at release: ", "离手附近手的位置"),
        ("raised_finish", "Raised-hand finish: ", "出手后抬手保持"),
    ]:
        if key in by_id:
            descriptions_en.append(intro_en + by_id[key]["display_value"]["en"].lower() + ".")
            descriptions_zh.append(intro_zh + by_id[key]["display_value"]["zh"] + "。")
    if coaching and (coaching["issues"] or coaching["strengths"] or coaching["coverage"]):
        summary = coaching["overall_summary"]
    elif available:
        tail = (
            bi(
                "Start with the optional practice point below and compare another set.",
                "先试下面的练习重点，再用下一组做对照。",
            )
            if issues
            else (
                bi(
                    "The available measurements do not establish a specific form fault. Review several comparable shots before choosing a correction.",
                    "现有测量还不足以确定具体技术问题，先比较几次同条件投篮，再决定需要改什么。",
                )
            )
        )
        summary = bi(" ".join(descriptions_en) + " " + tail["en"], "".join(descriptions_zh) + tail["zh"])
    else:
        summary = bi(
            "This clip does not yet provide enough clear evidence for a useful form judgment. Confirm the shooting hand and release moment, then review again.",
            "这段片段目前还缺少足够清晰的证据，暂时不能给出可靠的动作判断。先确认出手手和离手时刻，再复盘。",
        )
    if outcome == "awaiting_analysis":
        headline = bi("Your shooting review starts here", "从这一球开始复盘")
        summary = bi(
            "Analyze this shot to see its rhythm, release hand position and finish, followed by the most useful practice priorities.",
            "分析这一球后，先看出手节奏、手位和收势，再看最值得练习的重点。",
        )
    elif outcome == "model_failed":
        headline = empty_state["title"]
    elif issues:
        headline = issues[0]["title"]
    elif outcome == "no_priority_issue":
        headline = empty_state["title"]
    elif limited:
        headline = bi("A clearer release will make this review more useful", "看清离手，评价才能更具体")
    else:
        headline = bi("Your release rhythm and finish, at a glance", "先看懂这球的出手节奏与收势")
    if not coaching:
        limitations.append(
            bi(
                "Local tracking describes timing and arm motion. Guide-hand behavior, whole-body coordination and balance need clearer visual review before they can become coaching findings.",
                "本地识别主要描述时长与手臂运动；辅助手、全身协调和身体平衡还需要更清楚的视觉复核，才能形成具体建议。",
            )
        )
    if side_uncertain and has_analysis:
        limitations.append(
            bi(
                "The local tracker could not identify the shooting hand confidently. Arm-specific measurements and hand-dependent findings are withheld; cited visual observations of the movement remain available.",
                "本地识别尚不能确定出手侧，因此暂不展示依赖左右手的数值和问题判断；已有画面证据支持的整体动作观察仍然保留。",
            )
        )
    if phase_uncertain and has_analysis:
        limitations.append(
            bi(
                "The release interval is missing or too wide. Exact release metrics and separation-dependent findings are withheld; visual observations of the overall movement remain available.",
                "离手区间缺失或过宽，因此暂不展示精确出手指标和依赖离球瞬间的问题判断；整体动作的视觉观察仍然保留。",
            )
        )
    if model_stale:
        limitations.append(
            bi(
                "The saved visual review belongs to an earlier shot revision. It is not applied to the current timing or settings.",
                "已有视觉评价对应较早版本，尚未应用到当前时刻校准或设置。",
            )
        )
    if model_failed:
        limitations.append(_empty_state("model_failed")["detail"])
    if comparison and comparison.get("status") == "conditional_projection_comparison":
        limitations.append(
            bi(
                "The selected personal reference supports same-view descriptive comparison. It is not a validated standard shot and was not shown to the visual coach.",
                "选中的个人参照可用于同视角的描述性比较；它不是已验证的标准动作，也未提供给本次视觉教练。",
            )
        )
    elif comparison and comparison.get("status") not in (None, "no_reference"):
        limitations.append(
            bi(
                "The selected shot has not met the conditions for a numerical comparison; no difference is treated as a fault.",
                "选中的参照尚不满足数值比较条件，因此不把两球差别判作动作问题。",
            )
        )
    return {
        "version": "human-review-v2",
        "assessment_source": "model" if coaching else "measurements",
        "status": "awaiting_analysis"
        if outcome == "awaiting_analysis"
        else "limited"
        if limited
        else "reviewed",
        "outcome": outcome,
        "empty_state": empty_state,
        "coverage": {
            "model_review": "accepted"
            if coaching
            else "failed"
            if model_failed
            else "stale"
            if model_stale
            else "not_run",
            "available_metrics": len(available),
            "total_metrics": len(metrics),
            "withheld_dimensions": withheld_dimensions,
            "dimension_coverage": "reported" if coaching and coaching["coverage"] else "unspecified",
            "dimensions": coaching["coverage"] if coaching else [],
        },
        "overall": {"headline": headline, "summary": summary},
        "metrics": metrics,
        "strengths": strengths,
        "issues": issues,
        "next_practice": _next_practice(issues, outcome == "limited_visibility"),
        "limitations": limitations,
        "rubric_version": rubric["version"],
    }

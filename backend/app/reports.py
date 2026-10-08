from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .analysis import compare, release_anchor
from .coaching import build_review
from .config import ROOT
from .copy import labels
from .db import ident, now
from .perception import CONNECTIONS, visible


@lru_cache(maxsize=64)
def font(size, locale="en", bold=False):
    names = (
        [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        if locale == "zh"
        else []
    ) + [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in names:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def text(draw, position, value, size=22, locale="en", color="#1d4338", bold=False):
    draw.text(position, value, fill=color, font=font(size, locale, bold))


def formatted(metric):
    if metric["value"] is None:
        return "—"
    return f"{metric['value']:.0f}" if metric["unit"] == "milliseconds" else f"{metric['value']:.2f}"


@lru_cache(maxsize=8)
def schematic(size, locale):
    im = Image.new("RGB", size, "#e3ece3")
    d = ImageDraw.Draw(im)
    t = labels(locale)
    text(d, (24, 24), t["teaching"], 25, locale, bold=True)
    sx, sy = size[0] / 560, size[1] / 720

    def points(sequence):
        return [(round(x * sx), round(y * sy)) for x, y in sequence]

    d.ellipse(
        tuple(round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate([258, 205, 326, 273])),
        outline="#235c48",
        width=5,
    )
    for sequence in [
        [(290, 273), (282, 320), (314, 458)],
        [(278, 308), (231, 218), (187, 140), (166, 153)],
        [(314, 458), (278, 556), (302, 645), (260, 651)],
        [(314, 458), (357, 551), (387, 645), (348, 651)],
    ]:
        d.line(points(sequence), fill="#2b8770", width=7)
    text(d, (24, size[1] - 48), t["schematic_note"], 17, locale)
    return im


def display_crop(track, width, height):
    boxes = [f["person_box"] for f in track["frames"] if f.get("person_box")]
    if not boxes:
        return (0, 0, width, height)
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    body_height = y1 - y0
    pad = body_height * 0.28
    # Keep a fixed crop throughout the shot so body motion is not cancelled by a moving crop.
    return (
        max(0, int(x0 - pad)),
        max(0, int(y0 - pad)),
        min(width, int(x1 + pad)),
        min(height, int(y1 + pad)),
    )


def frame_image(settings, asset, track, relative, anchor, color, size=(640, 480)):
    target = max(0, min(asset["frame_index"][-1]["time_us"], anchor + relative * 1e6))
    index = min(
        range(len(asset["frame_index"])), key=lambda n: abs(asset["frame_index"][n]["time_us"] - target)
    )
    info = asset["frame_index"][index]
    with Image.open(settings.resolve(info["path"])) as raw:
        source = raw.convert("RGB")
    crop = display_crop(track, source.width, source.height) if track else (0, 0, source.width, source.height)
    cropped = source.crop(crop)
    canvas = Image.new("RGB", size, "#13231e")
    image = ImageOps.contain(cropped, size)
    offset = ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
    canvas.paste(image, offset)
    d = ImageDraw.Draw(canvas)
    f = track["frames"][index] if track else None
    if f and f.get("landmarks"):
        points = f["landmarks"]
        for a, b in CONNECTIONS:
            if visible(points[a]) and visible(points[b]):
                d.line(
                    [
                        (
                            offset[0]
                            + (points[a]["x"] * source.width - crop[0]) * image.width / cropped.width,
                            offset[1]
                            + (points[a]["y"] * source.height - crop[1]) * image.height / cropped.height,
                        ),
                        (
                            offset[0]
                            + (points[b]["x"] * source.width - crop[0]) * image.width / cropped.width,
                            offset[1]
                            + (points[b]["y"] * source.height - crop[1]) * image.height / cropped.height,
                        ),
                    ],
                    fill=color,
                    width=3,
                )
        for p in points:
            if visible(p):
                x, y = (
                    offset[0] + (p["x"] * source.width - crop[0]) * image.width / cropped.width,
                    offset[1] + (p["y"] * source.height - crop[1]) * image.height / cropped.height,
                )
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
        ball = f.get("ball")
        if ball:
            x, y = (
                offset[0] + (ball["x"] * source.width - crop[0]) * image.width / cropped.width,
                offset[1] + (ball["y"] * source.height - crop[1]) * image.height / cropped.height,
            )
            r = ball["radius_px"] * image.width / cropped.width
            d.ellipse((x - r, y - r, x + r, y + r), outline="#f5ce68", width=3)
    return canvas, {
        "asset_id": asset["id"],
        "frame_id": info["frame_id"],
        "frame_index": index,
        "source_frame_index": info["source_frame_index"],
        "source_time_us": info["source_time_us"],
        "clip_time_us": info["time_us"],
        "displayed_relative_s": (info["time_us"] - anchor) / 1e6,
        "source_crop_box_px": list(crop),
    }


def local_text(value, locale):
    return value.get(locale, value.get("en", "")) if isinstance(value, dict) else str(value)


def paragraph(draw, position, value, width, size=22, locale="en", color="#1d4338", lines=3):
    words = list(value) if locale == "zh" else value.split(" ")
    separator = "" if locale == "zh" else " "
    rows, current = [], ""
    face = font(size, locale)
    for word in words:
        trial = current + separator + word if current else word
        if draw.textlength(trial, font=face) > width and current:
            rows.append(current)
            current = word
        else:
            current = trial
    if current:
        rows.append(current)
    if len(rows) > lines:
        rows = rows[:lines]
        while rows[-1] and draw.textlength(rows[-1] + "…", font=face) > width:
            rows[-1] = rows[-1][:-1]
        rows[-1] += "…"
    for index, row in enumerate(rows):
        text(draw, (position[0], position[1] + index * (size + 8)), row, size, locale, color)
    return len(rows) * (size + 8)


def build_report(
    settings,
    asset,
    track,
    reference=None,
    ref_track=None,
    locale="en",
    assume_same_view=False,
    cancelled=None,
):
    t = labels(locale)
    own = asset["measurements"]
    comparison = compare(
        asset, own, reference, reference.get("measurements") if reference else None, assume_same_view
    )
    review = build_review(asset, comparison)

    def pick(value):
        return local_text(value, locale)

    words = (
        {
            "priorities": "主要关注点",
            "metrics": "这球的动作数据",
            "next": "下一组怎么练",
            "check": "回看时检查",
            "goal": "教学目标与差别",
            "why": "为什么关注",
            "action": "怎么调整",
            "drill": "练习方法",
            "limits": "当前画面的判断范围",
            "strengths": "可以保留的动作",
            "evidence": "证据源时间",
            "high": "优先处理",
            "medium": "建议先看",
            "low": "细节练习",
            "source": "教学依据",
            "footer": "建议依据当前画面，需结合相同条件的多次投篮复核。",
        }
        if locale == "zh"
        else {
            "priorities": "Main priorities",
            "metrics": "Movement at a glance",
            "next": "Your next practice",
            "check": "What to check",
            "goal": "Teaching goal and visible gap",
            "why": "Why it matters",
            "action": "What to change",
            "drill": "Practice",
            "limits": "What this clip supports",
            "strengths": "What to keep",
            "evidence": "Source evidence time",
            "high": "First priority",
            "medium": "Review next",
            "low": "Optional refinement",
            "source": "Teaching sources",
            "footer": "Suggestions use this view; confirm them across matched attempts.",
        }
    )
    key = ident("report")
    folder = settings.data_dir / "reports" / key
    folder.mkdir(parents=True)
    items = [
        {
            "id": i["id"],
            "attribute": i["rubric_id"],
            "kind": "coaching_priority",
            "evidence_frame_ids": i["evidence_frame_ids"],
            "source_ids": i["source_ids"],
            "severity": i["severity"],
            "confidence": i["confidence"],
            "coaching_status": "provisional",
        }
        for i in review["issues"]
    ]
    body = {
        "id": key,
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "created_at": now(),
        "locale": locale,
        "phase_revision": asset["revision"],
        "phases": asset["phases"],
        "local_phase_proposal": asset.get("local_phase_proposal"),
        "model_assist": asset.get("model_assist"),
        "analysis_config": asset.get("analysis_config"),
        "reference_id": reference["id"] if reference else None,
        "reference_revision": reference["revision"] if reference else None,
        "comparison": comparison,
        "measurements": own["measurements"],
        "findings": items,
        "coaching": review,
        "flags": own["flags"],
        "coordinate_system": "image_projection",
        "coaching_status": "provisional",
        "cause_of_miss": None,
        "world_coordinates_validated": False,
        "measured_curry_motion": False,
    }
    catalog = json.loads((ROOT / "references/sources.json").read_text())
    source_ids = {source for issue in review["issues"] for source in issue["source_ids"]} | {
        "curry-mechanics",
        "curry-form-practice",
        "jr-nba-shooting",
    }
    body["sources"] = [source for source in catalog if source["id"] in source_ids]
    by_id = {frame["frame_id"]: frame for frame in asset["frame_index"]}

    def evidence_line(ids):
        times = sorted(by_id[key]["source_time_us"] / 1e6 for key in ids if key in by_id)
        return f"{words['evidence']}: {times[0]:.3f}–{times[-1]:.3f}s" if times else ""

    report_text = [
        f"# {t['title']} — {asset['label']}",
        f"{t['revision']}: {asset['revision']}",
        "",
        "## " + pick(review["overall"]["headline"]),
        pick(review["overall"]["summary"]),
    ]
    if review["issues"]:
        report_text += ["", "## " + words["priorities"]]
        for issue in review["issues"]:
            report_text += [
                "",
                f"### {issue['rank']}. {pick(issue['title'])} · {words[issue['severity']]}",
                pick(issue["observation"]),
            ]
            for name, label in [
                ("standard_gap", "goal"),
                ("why_it_matters", "why"),
                ("action", "action"),
                ("drill", "drill"),
            ]:
                report_text.append(f"- **{words[label]}**：{pick(issue[name])}")
            report_text.append(evidence_line(issue["evidence_frame_ids"]))
    if review["strengths"]:
        report_text += ["", "## " + words["strengths"]]
        report_text += [
            f"- **{pick(item['title'])}**：{pick(item['detail'])}" for item in review["strengths"]
        ]
    report_text += ["", "## " + words["metrics"]]
    report_text += [
        f"- **{pick(metric['label'])}：{pick(metric['display_value'])}**。{pick(metric['interpretation'])}"
        for metric in review["metrics"]
    ]
    plan = review["next_practice"]
    report_text += [
        "",
        "## " + words["next"],
        "**" + pick(plan["title"]) + "**",
        pick(plan["instruction"]),
        f"{words['check']}：{pick(plan['success_check'])}",
        "",
        "## " + words["limits"],
    ]
    report_text += ["- " + pick(item) for item in review["limitations"]]
    report_text += ["", "## " + words["source"]]
    report_text += [f"- [{source.get('title', source['id'])}]({source['url']})" for source in body["sources"]]
    (folder / "report.md").write_text("\n".join(report_text) + "\n")
    anchor = release_anchor(asset["phases"])
    basis = "release" if anchor is not None else "extension_peak"
    if anchor is None:
        peak = asset["phases"].get("extension_peak")
        anchor = sum(peak["range_us"]) / 2 if peak else asset["duration_us"] / 2
    ref_anchor = release_anchor(reference["phases"]) if reference else None
    if reference and ref_anchor is None:
        peak = reference["phases"].get("extension_peak")
        ref_anchor = sum(peak["range_us"]) / 2 if peak else reference["duration_us"] / 2

    def compose(relative):
        canvas = Image.new("RGB", (1280, 1000), "#f1f4ee")
        d = ImageDraw.Draw(canvas)
        text(d, (24, 18), f"{t['title']} · {asset['label']}", 28, locale, bold=True)
        text(d, (1080, 24), f"{t['revision']} {asset['revision']}", 17, locale)
        paragraph(d, (24, 64), pick(review["overall"]["headline"]), 1210, 27, locale, lines=1)
        text(d, (24, 112), asset["label"][:40], 21, locale, bold=True)
        text(d, (664, 112), (reference["label"] if reference else t["teaching"])[:40], 21, locale, bold=True)
        a, evidence_a = frame_image(settings, asset, track, relative, anchor, "#db9850", size=(640, 440))
        b, evidence_b = (
            frame_image(settings, reference, ref_track, relative, ref_anchor, "#5daa89", size=(640, 440))
            if reference
            else (schematic((640, 440), locale), None)
        )
        basis_label = t["release"] if basis == "release" else t["extension"]
        text(
            d,
            (24, 140),
            f"{basis_label} {evidence_a['displayed_relative_s']:+.2f}s · {t['source']} {evidence_a['source_time_us'] / 1e6:.3f}s",
            14,
            locale,
        )
        if evidence_b:
            text(d, (664, 140), f"{t['source']} {evidence_b['source_time_us'] / 1e6:.3f}s", 14, locale)
        canvas.paste(a, (0, 162))
        canvas.paste(b, (640, 162))
        for n, metric in enumerate(review["metrics"][:4]):
            x = 24 + n * 315
            d.rounded_rectangle((x, 624, x + 291, 757), radius=8, fill="#e4ebde")
            paragraph(d, (x + 14, 638), pick(metric["label"]), 263, 18, locale, lines=2)
            paragraph(d, (x + 14, 690), pick(metric["display_value"]), 263, 22, locale, lines=2)
        issue = review["issues"][0] if review["issues"] else None
        headline = words[issue["severity"]] + " · " + pick(issue["title"]) if issue else pick(plan["title"])
        action = pick(issue["action"]) if issue else pick(plan["instruction"])
        paragraph(d, (24, 789), headline, 1215, 25, locale, lines=1)
        paragraph(d, (24, 835), action, 1215, 21, locale, lines=3)
        text(d, (24, 963), words["footer"], 16, locale, color="#617362")
        return canvas, [item for item in (evidence_a, evidence_b) if item]

    still, image_evidence = compose(0.7)
    still.save(folder / "comparison.jpg", quality=93)
    body["image_evidence"] = image_evidence
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "1280x1000",
            "-r",
            "25",
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(folder / "comparison.mp4"),
        ],
        stdin=subprocess.PIPE,
    )
    video_evidence = []
    try:
        for index in range(200):
            if cancelled and cancelled():
                raise InterruptedError("cancelled")
            frame, evidence = compose(max(-0.6, min(0.8, -0.6 + (index / 25 - 1) * 0.4)))
            process.stdin.write(frame.tobytes())
            video_evidence.append({"output_frame": index, "output_time_s": index / 25, "evidence": evidence})
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Video export failed")
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    body["video_evidence"] = video_evidence
    body["render"] = {
        "fps": 25,
        "duration_s": 8,
        "width": 1280,
        "height": 1000,
        "slow_motion_speed": 0.4,
        "alignment_basis": basis,
        "reference_alignment_basis": "release"
        if reference and release_anchor(reference["phases"]) is not None
        else "extension_candidate"
        if reference
        else "schematic",
        "missing_context_policy": "clamp_to_available_frame_and_record_displayed_time",
    }
    body["artifacts"] = {
        name: str((folder / file).relative_to(settings.data_dir))
        for name, file in [
            ("image", "comparison.jpg"),
            ("video", "comparison.mp4"),
            ("text", "report.md"),
            ("json", "report.json"),
        ]
    }
    (folder / "report.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    return body

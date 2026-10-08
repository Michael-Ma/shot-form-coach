from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .analysis import compare, findings, release_anchor
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
    items = findings(own, comparison)
    key = ident("report")
    folder = settings.data_dir / "reports" / key
    folder.mkdir(parents=True)
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
        "flags": own["flags"],
        "coordinate_system": "image_projection",
        "coaching_status": "hypothesis_to_test",
        "cause_of_miss": None,
        "world_coordinates_validated": False,
        "measured_curry_motion": False,
    }
    sources = json.loads((ROOT / "references/sources.json").read_text())
    source_ids = {s for f in items for s in f["source_ids"]}
    body["sources"] = [s for s in sources if s["id"] in source_ids]
    anchor = release_anchor(asset["phases"])
    basis = "release" if anchor is not None else "extension_peak"
    if anchor is None:
        peak = asset["phases"].get("extension_peak")
        anchor = sum(peak["range_us"]) / 2 if peak else asset["duration_us"] / 2
    ref_anchor = release_anchor(reference["phases"]) if reference else None
    if reference and ref_anchor is None:
        peak = reference["phases"].get("extension_peak")
        ref_anchor = sum(peak["range_us"]) / 2 if peak else reference["duration_us"] / 2
    report_text = [
        f"# {t['title']} — {asset['label']}",
        f"{t['revision']}: {asset['revision']}",
        t["projection"],
        "",
    ]
    for m in own["measurements"]:
        note = t.get(m["reason"], "") if m.get("reason") else ""
        report_text.append(f"- {t[m['key']]}: {formatted(m)} {t[m['unit']]} {note}")
    release = asset["phases"].get("release")
    report_text += [
        "",
        f"{t['release']}: "
        + (" – ".join(f"{v / 1e6:.3f}s" for v in release["range_us"]) if release else t["unknown"]),
        f"{t['reference']}: {reference['label'] if reference else t['no_ref']}",
    ]
    for difference in comparison["differences"]:
        report_text.append(
            f"- {t[difference['key']]}: {difference['value']:.2f} / "
            f"{difference['reference_value']:.2f}; Δ {difference['difference']:+.2f} {t[difference['unit']]}"
        )
    report_text += ["", t["hypothesis"]]
    for f in items:
        report_text += [f"- {t[f['cue_id']]}", f"  evidence: {', '.join(f['evidence_frame_ids'])}"]
    for flag in own["flags"]:
        report_text += [t.get(flag, flag)]
    if comparison.get("reason") in t:
        report_text += [t[comparison["reason"]]]
    if not items:
        report_text += [t.get("release_unknown") if "release_unknown" in own["flags"] else t["track_gaps"]]
    report_text += ["", t["limits"], t["phase_note"], "", "Sources:"]
    report_text += [f"- {s.get('title', s['id'])}: {s['url']}" for s in body["sources"]]
    (folder / "report.md").write_text("\n".join(report_text) + "\n")

    def compose(relative):
        canvas = Image.new("RGB", (1280, 840), "#f1f4ee")
        d = ImageDraw.Draw(canvas)
        text(d, (24, 16), t["title"], 29, locale, bold=True)
        text(d, (760, 22), f"{t['revision']} {asset['revision']}  |  {t['projection']}", 18, locale)
        text(d, (24, 65), asset["label"][:45], 24, locale, bold=True)
        text(d, (664, 65), (reference["label"] if reference else t["teaching"])[:45], 24, locale, bold=True)
        a, ref_a = frame_image(settings, asset, track, relative, anchor, "#db9850")
        b, ref_b = (
            frame_image(settings, reference, ref_track, relative, ref_anchor, "#5daa89")
            if reference
            else (schematic((640, 480), locale), None)
        )
        canvas.paste(a, (0, 114))
        canvas.paste(b, (640, 114))
        basis_label = t["release"] if basis == "release" else t["extension"]
        text(
            d,
            (24, 99),
            f"{basis_label}: {ref_a['displayed_relative_s']:+.2f}s  /  {t['source']} {ref_a['source_time_us'] / 1e6:.3f}s",
            15,
            locale,
        )
        if ref_b:
            text(d, (664, 99), f"{t['source']} {ref_b['source_time_us'] / 1e6:.3f}s", 15, locale)
        y = 620
        for m in own["measurements"][:4]:
            # Four readable rows, kept away from the source pixels.
            text(d, (24, y), f"{t[m['key']]}: {formatted(m)} {t[m['unit']]}", 20, locale)
            y += 30
        for row, difference in enumerate(comparison["differences"][:4]):
            text(
                d,
                (664, 620 + row * 30),
                f"{t[difference['key']]}: {difference['reference_value']:.2f}"
                f"  / Δ {difference['difference']:+.2f}",
                18,
                locale,
            )
        text(d, (24, 755), t["hypothesis"], 21, locale, color="#28644e", bold=True)
        text(d, (24, 800), t["phase_note"], 17, locale, color="#52685e")
        return canvas, [r for r in [ref_a, ref_b] if r]

    image, image_refs = compose(0.7)
    image.save(folder / "comparison.jpg", quality=93)
    body["image_evidence"] = image_refs
    movie = folder / "comparison.mp4"
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
            "1280x840",
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
            str(movie),
        ],
        stdin=subprocess.PIPE,
    )
    evidence = []
    try:
        for index in range(200):
            if cancelled and cancelled():
                raise InterruptedError("cancelled")
            relative = max(-0.6, min(0.8, -0.6 + (index / 25 - 1) * 0.4))
            frame, refs = compose(relative)
            process.stdin.write(frame.tobytes())
            evidence.append({"output_frame": index, "output_time_s": index / 25, "evidence": refs})
    except BaseException:
        process.stdin.close()
        process.terminate()
        process.wait()
        raise
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("Video export failed")
    body["video_evidence"] = evidence
    body["render"] = {
        "fps": 25,
        "duration_s": 8,
        "slow_motion_speed": 0.4,
        "alignment_basis": basis,
        "reference_alignment_basis": (
            "release"
            if reference and release_anchor(reference["phases"]) is not None
            else "extension_candidate"
            if reference
            else "schematic"
        ),
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

"""Render the design example from existing Workbench clips; no model inference.

Annotations are authored in review-spec.json and are pending independent coach review.
The renderer preserves frame provenance and does not label the comparator as an ideal shot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, PANEL_W, PANEL_H, TOP, BOTTOM = 1680, 560, 720, 132, 168
HEIGHT = TOP + PANEL_H + BOTTOM
BG, INK, MUTED = '#f3f5f1', '#183c34', '#53675f'
ORANGE, GREEN = '#cf762d', '#2b8770'


def command(args: list[str]) -> None:
    subprocess.run(args, check=True)


def read_json(path: Path):
    return json.loads(path.read_text())


def font(size: int, bold: bool = False):
    names = ([
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    ] if bold else [
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ])
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def line(draw, xy, text, size=22, fill=INK, bold=False):
    draw.text(xy, text, font=font(size, bold), fill=fill)


def teaching_panel() -> Image.Image:
    im = Image.new('RGB', (PANEL_W, PANEL_H), '#e6eee7')
    d = ImageDraw.Draw(im)
    line(d, (30, 25), 'ONE TRAINING CUE TO TEST', 20, GREEN, True)
    line(d, (30, 65), 'A relaxed, extended finish', 26, INK, True)
    # Original pedagogical drawing, not extracted or measured reference motion.
    d.line([(74, 241), (474, 241)], fill='#becdc0', width=2)
    d.ellipse((258, 205, 326, 273), outline=INK, width=6)
    d.ellipse((264, 229, 270, 235), fill=INK)
    d.line([(290, 273), (282, 320), (314, 458)], fill=INK, width=8)
    d.line([(278, 308), (231, 218), (187, 140), (166, 153)], fill=GREEN, width=10)
    d.line([(293, 313), (354, 289), (340, 218)], fill='#8caa99', width=7)
    d.line([(314, 458), (278, 556), (302, 645), (260, 651)], fill=INK, width=8)
    d.line([(314, 458), (357, 551), (387, 645), (348, 651)], fill=INK, width=8)
    d.line([(205, 110), (233, 127)], fill=GREEN, width=3)
    line(d, (242, 107), 'Finish the motion', 19, GREEN)
    line(d, (30, 674), 'Schematic only - no measured Curry pose', 18, MUTED)
    return im


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbench-data', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('examples'))
    parser.add_argument('--spec', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'examples/review-spec.json')
    args = parser.parse_args()
    for binary in ['ffmpeg', 'ffprobe']:
        if not shutil.which(binary):
            raise SystemExit(f'{binary} is required')
    spec = read_json(args.spec)
    data_root, out = args.workbench_data.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache = out / '.render-cache'
    cache.mkdir(exist_ok=True)
    results = read_json(data_root / 'runs' / spec['source_run_id'] / 'results.json')
    events = {e['event_id']: e for e in results['events']}
    assets = []
    for i, shot in enumerate(spec['shots']):
        event = events[shot['event_id']]
        path = (data_root / event['clip']['path']).resolve()
        if not path.is_relative_to(data_root) or not path.is_file():
            raise SystemExit('Clip path is outside the data directory or unavailable')
        probe = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
            '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path),
        ]))
        pts = [float(f['best_effort_timestamp_time']) for f in probe['frames']]
        folder = cache / str(i)
        folder.mkdir(exist_ok=True)
        x, y, w, h = shot['crop_xywh']
        command(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-vf',
                 f'crop={w}:{h}:{x}:{y}', '-fps_mode', 'passthrough', str(folder / '%04d.png')])
        images = sorted(folder.glob('*.png'))
        if len(images) != len(pts):
            raise SystemExit('Decoded images do not match the frame timestamp index')
        assets.append({
            'shot': shot, 'event': event, 'pts': pts, 'images': images,
            'origin_us': event['clip']['actual_range_us'][0],
            'release_us': sum(shot['release_interval_source_us']) / 2,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })

    schematic = teaching_panel()
    render = spec['render']

    def compose(relative_s: float):
        im = Image.new('RGB', (WIDTH, HEIGHT), BG)
        d = ImageDraw.Draw(im)
        line(d, (28, 19), 'SHOT FORM COACH', 27, INK, True)
        line(d, (380, 23), 'Visual-review design example  |  Independent coach review pending', 20, MUTED)
        titles = ['Shot 1 - rep to review', 'Shot 2 - personal comparator', 'Teaching reference - schematic']
        for i, title in enumerate(titles):
            line(d, (i * PANEL_W + 26, 66), title, 25, INK, True)
        frame_records = []
        for i, a in enumerate(assets):
            target = (a['release_us'] - a['origin_us']) / 1e6 + relative_s
            if target < a['pts'][0] - .04 or target > a['pts'][-1] + .04:
                raise ValueError('Requested phase window extends beyond an available clip')
            n = min(range(len(a['pts'])), key=lambda j: abs(a['pts'][j] - target))
            with Image.open(a['images'][n]) as original:
                frame = original.convert('RGB')
            im.paste(frame, (i * PANEL_W, TOP))
            source_us = a['origin_us'] + round(a['pts'][n] * 1e6)
            line(d, (i * PANEL_W + 26, 103), f'Source {source_us/1e6:.3f}s  |  approximately {relative_s:+.2f}s from release', 17, MUTED)
            if relative_s >= .4:
                x, y, w, h = a['shot']['highlight_crop_xywh']
                color = ORANGE if i == 0 else GREEN
                d.rounded_rectangle((i*PANEL_W+x, TOP+y, i*PANEL_W+x+w, TOP+y+h),
                                    radius=15, outline=color, width=5)
            frame_records.append({
                'event_id': a['shot']['event_id'], 'clip_frame_index': n,
                'source_frame_index': a['event']['clip']['metadata']['source_first_frame']['frame_index'] + n,
                'source_time_us': source_us,
            })
        im.paste(schematic, (2 * PANEL_W, TOP))
        d.line([(560, TOP), (560, TOP+PANEL_H)], fill=BG, width=5)
        d.line([(1120, TOP), (1120, TOP+PANEL_H)], fill=BG, width=5)
        footer_y = TOP + PANEL_H
        d.rectangle((0, footer_y, WIDTH, HEIGHT), fill=INK)
        if relative_s < 0:
            headline = 'Compare the same movement phase, not the same file timestamp.'
        else:
            headline = 'Candidate practice focus: a more repeatable follow-through finish.'
        line(d, (30, footer_y+22), headline, 29, '#ffffff', True)
        line(d, (30, footer_y+72), 'The difference is visible; whether this cue helps your shooting still needs a matched retest.', 23, '#d5e5dc')
        line(d, (30, footer_y+119), 'Sources: existing Workbench clips + Curry / MasterClass teaching. Boxes are review regions, not pose measurements.', 18, '#b4ccc0')
        return im, frame_records

    still, still_frames = compose(render['still_relative_to_release_s'])
    still.save(out / 'follow-through-comparison.jpg', quality=94)
    fps = render['output_fps']
    left, right = render['video_relative_range_s']
    motion_s = (right - left) / render['slow_motion_speed']
    total_s = render['intro_hold_s'] + motion_s + render['end_hold_s']
    video = out / 'follow-through-comparison.mp4'
    proc = subprocess.Popen([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{WIDTH}x{HEIGHT}', '-r', str(fps), '-i', 'pipe:0',
        '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', str(video),
    ], stdin=subprocess.PIPE)
    rendered_frames = []
    try:
        for index in range(round(total_s * fps)):
            time_s = index / fps
            phase = min(right, max(left, left + (time_s-render['intro_hold_s']) * render['slow_motion_speed']))
            image, refs = compose(phase)
            ImageDraw.Draw(image).text((1150, 104), '0.4x playback / phase-aligned example',
                                       font=font(17), fill=MUTED)
            proc.stdin.write(image.tobytes())
            rendered_frames.append({'output_frame': index, 'output_time_s': time_s,
                                    'relative_to_release_s': phase, 'evidence': refs})
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit('Video encoder failed')
    manifest = {
        'schema_version': 'render-evidence/v1', 'finding_id': spec['finding_id'],
        'annotation_source': spec['annotation_source'], 'status': spec['status'],
        'source_run_id': spec['source_run_id'], 'fps': fps, 'duration_s': total_s,
        'source_assets': [{'event_id': a['shot']['event_id'], 'sha256': a['sha256'],
                           'clip_origin_source_us': a['origin_us'],
                           'release_interval_source_us': a['shot']['release_interval_source_us']}
                          for a in assets],
        'still_evidence': still_frames, 'video_evidence': rendered_frames,
        'numerical_pose_measurements': None, 'measured_curry_motion': False,
    }
    (out / 'render-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'image': str(out/'follow-through-comparison.jpg'), 'video': str(video),
                      'duration_s': total_s, 'frames': len(rendered_frames)}))


if __name__ == '__main__':
    main()

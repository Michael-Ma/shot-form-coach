# Shot Form Coach

A local basketball shooting review app with traceable movement measurements, optional
phase correction, and written, image, and video reports. This is a separate project from
[Video Event Workbench](https://github.com/Michael-Ma/video-event-workbench).

**Status: runnable engineering V1.** The local vision workflow has been exercised on six
real shooting clips. Coaching accuracy and training effectiveness require further validation.
The optional Gemini adapter has boundary tests; a live paid call has not been tested here.

## Run locally

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node.js/npm, FFmpeg and ffprobe.
The current build was validated on macOS Apple Silicon.

```sh
cp .env.example .env
./start.sh
```

Open **http://127.0.0.1:5184/**. The API runs on **127.0.0.1:8002**; the launcher checks for
conflicting listeners and stops only its own children. Initial startup installs locked
dependencies and downloads checksum-pinned MediaPipe and YOLOX models (about 45 MB).
Use Ctrl+C to stop. Local analysis requires no API key and makes no model API calls.

To import existing Workbench clips, set `SFC_WORKBENCH_DATA` in `.env` to the absolute path
of that project's `.data` directory. Otherwise upload a video of one shot, at most 30 seconds.
Clips are copied into this project's data directory, with their original frame timestamps.

## Try the workflow

1. Import a clip or a Workbench run. Import automatically queues analysis using the selected
   shooting hand, camera view, shot context, and analysis method.
2. Inspect the body and ball candidates, release interval, and wrist-height curve. Toggle
   movement focus to see the full source frame.
3. Optionally step to the last contact and first clear separation, select both, and save.
   Corrections keep the original proposal, create a revision, and rebuild the report from
   cached tracks. An unknown interval remains unknown until evidence supports it.
4. Select another analyzed shot as a personal comparator. Numerical differences require
   matching hand/context and a matching or explicitly assumed fixed camera view. A comparator
   supplies an attribute example; it is not automatically an ideal technique.
5. Update the comparison to generate the current language's report. Download Markdown,
   comparison JPEG, 8-second H.264 slow-motion MP4, or the evidence JSON. Each movie frame
   records its source frame, timestamp, displayed relative time, and crop transformation.

The interface supports English and Chinese. A release correction rebuilds exports in the
current interface language; switching language alone preserves the existing exported report
until **Update comparison & exports** is selected.

The first measurable loop concerns follow-through and personal repeatability: projected
wrist height in two post-release windows, its change, projected elbow-angle change, and
loading-to-release timing. Missing body points or later context produce unavailable values,
not zero. The UI gives one practice hypothesis to test in a matched retake.

## Optional model assistance

Set `GEMINI_API_KEY` on the server and choose **Local + Gemini**. The V1 adapter uses ordered
JPEG frames with explicit frame identifiers (up to 80 by default), not native-video transport.
It adds an evidence-checked phase candidate and structured observations; the local vision
tracks still provide all numerical measurements. Astra and Qwen remain evaluation candidates.

Each job permits at most six model calls by default and each call allows 16,000 output tokens.
Intent, exact input frame IDs, response, usage, and a versioned list-price estimate are saved.
There is no automatic retry. Usage survives invalid replies and cancellation after a response.
An unknown request outcome keeps its cost unknown and blocks another paid request for that
asset. Local analysis remains available. These estimates are not billing receipts.

## Design and implementation

- [Improved design, current V1 scope](docs/DESIGN_V2.zh-CN.md)
- [Step-by-step implementation plan and status](docs/IMPLEMENTATION_PLAN.zh-CN.md)
- [Engineering V1 validation](docs/VALIDATION_V1.md)
- [MediaPipe, coaching studies, and model research](docs/RESEARCH_COACHING_AND_MODELS.zh-CN.md)
- [Curry teaching and reference research](docs/RESEARCH.zh-CN.md)
- [Model evaluation plan](docs/MODEL_EVALUATION.zh-CN.md)
- [Reference versus individual target](docs/ADR-0001-reference-target.md)
- [Optional phase correction](docs/ADR-0002-optional-phase-correction.md)
- [Source catalog](references/sources.json)

## Checks

```sh
uv sync --locked --extra dev --python 3.12
.venv/bin/pytest -q
.venv/bin/ruff check backend
npm ci --prefix web
npm run build --prefix web
```

Private media, model binaries, runtime reports, API keys, and dependency folders are ignored
by Git. Models are downloaded from the publishers' URLs recorded in `models/manifest.json`.
YOLOX model attribution/license is in `models/YOLOX-LICENSE`.

## What the evidence means

Body landmarks and sports-ball detections are estimates. Current measurements describe the
visible image projection; they do not measure true 3D joint angles, force, spin, finger pressure,
or the cause of a missed shot. Curry's published teaching supplies principles, and an original
schematic illustrates a cue. No measured Curry motion is shipped as a universal target.

The six existing clips check engineering behavior. Model rankings need independent labels
across sessions and camera views; improvement claims need matched training, unprompted and
cross-day retests. Foot/body stability metrics, filters, calibrated trajectories, and 3D animation
are later extensions with their own acceptance criteria.

## Earlier visual-design example

[Annotated example image](examples/follow-through-comparison.jpg) ·
[Video](examples/follow-through-comparison.mp4) ·
[Interpretation](docs/SAMPLE_REVIEW.zh-CN.md)

This earlier example was annotated by visual inspection and remains a design reference,
separate from the new automatic engine. To reproduce it, use `scripts/render_example.py`
with your Workbench data directory and `requirements-render.txt`.

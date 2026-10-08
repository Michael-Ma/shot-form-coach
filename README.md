# Shot Form Coach

A local basketball shooting review app with traceable movement measurements, optional
phase correction, and written, image, and video reports. This is a separate project from
[Video Event Workbench](https://github.com/Michael-Ma/video-event-workbench).

**Status: runnable engineering V1.** The local vision workflow has been exercised on six
real shooting clips. Coaching accuracy and training effectiveness require further validation.
Gemini and Astra are selectable. Astra supports the OpenAI API and a signed-in Codex CLI.
The Codex transport has a successful live check on synthetic images; private shooting clips
have not been sent through it in this validation run.

## Run locally

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node.js/npm, FFmpeg and ffprobe.
The current build was validated on macOS Apple Silicon.

```sh
./start.sh
```

The script creates `.env` if missing, installs locked dependencies, validates/downloads the
vision models, starts the API, background worker and UI, and opens the browser once ready.
On macOS, you can also double-click `start.command`.

```sh
./start.sh --check     # Check model/auth readiness, without starting servers
./start.sh --no-open   # Start everything without opening a browser
```

Repeating startup reuses a running version of this app. An occupied port belonging to another
instance produces a clear error; no other project is stopped. Edit `.env` to configure API keys.

Open **http://127.0.0.1:5184/**. The API runs on **127.0.0.1:8002**; the launcher checks for
conflicting listeners and stops only its own children. Initial startup installs locked
dependencies and downloads checksum-pinned MediaPipe and YOLOX models (about 45 MB).
Use Ctrl+C to stop. Local analysis requires no API key and makes no model API calls.

To import existing Workbench clips, set `SFC_WORKBENCH_DATA` in `.env` to the absolute path
of that project's `.data` directory. Otherwise upload a video of one shot, at most 30 seconds.
Clips are copied into this project's data directory, with their original frame timestamps.

## A review you can use at your next practice

The main screen starts with an overall takeaway, up to three ranked practice priorities,
a next-set plan, and four understandable movement metrics. Each issue connects what is visible
to a sourced teaching goal, a suggested change, a drill, and the original video evidence.
Priority and evidence confidence are separate; missing evidence does not become a fault or a score.

The main metrics are dip-to-release time, hand position around release, observed raised-hand
finish duration, and post-release hand movement. Technical measurements, phase correction,
comparators, sources, exports and activity/costs remain available in expandable details.

Local vision produces a clearly labelled **movement summary**. Gemini/Astra can additionally
produce a bilingual **visual coaching review** using the supplied teaching rubric, measured
context and input frames. Analysis, import, comparison, playback and language settings share the top-right Settings drawer.
The page shows the selected method beside the analysis action. The app remembers an explicit
choice but never starts a remote request simply because a selection or page changes.

Current automatic priorities remain provisional. The system does not force three problems,
assign a universal form score, claim measured Curry motion or diagnose the cause of a miss.
The teaching goals are server-controlled; the model cannot silently redefine the standard.

## Try the workflow

1. Open **Settings** at the top right to choose the analysis method and import a clip.
   **Import pre-cut shots** reads completed exports from Video Event Workbench and preserves
   their original video times; it is a clip source, not another analysis model.
   Import automatically queues analysis using the selected
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

The first measurable loop concerns release rhythm and the visible finish. Detailed views
retain projected wrist and elbow measurements; the main view translates them into movement
terms and explains the limits of each observation. Missing body points or later context produce unavailable values,
not zero. The UI gives one practice hypothesis to test in a matched retake.

## Choose Gemini or Astra

All modes retain the local body/ball tracks and numerical measurements. The model adds an
evidence-checked release candidate and structured observations, linked to the input frames.
The UI supports these choices:

| Analysis mode | Authentication | Usage |
| --- | --- | --- |
| Local vision | None | No model API charge |
| Gemini | `GEMINI_API_KEY` | Gemini API billing |
| Astra (Codex) | Existing ChatGPT sign-in in Codex | Your Codex plan and usage limits |
| Astra (API) | `OPENAI_API_KEY` | OpenAI API billing |

Astra's requested model is `gpt-6-astra`. It receives timestamped JPEG frames; Astra's API
supports images, not native video. The default maximum is 80 frames per clip, shared with
Gemini. See [Astra model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra).

**Astra through Codex needs no OpenAI API key.** The app looks for a working `codex` executable
and can use the Codex bundled with the ChatGPT/Codex desktop app. Set `SFC_CODEX_BIN` only if
a specific executable is needed. Install a recent Codex CLI and run `codex login` with ChatGPT
if you are not signed in. Startup reports readiness; unavailable modes are disabled.

The runner uses `codex exec --image --json --output-schema`, an ephemeral session, read-only
sandbox, disabled shell/apps/multi-agent tools, and explicit zero HTTP/stream retry settings.
It ignores personal/project configuration for the analysis and uses saved ChatGPT authentication;
it does not copy your login tokens into this repository. Inputs, local execution events, the final
JSON and token usage are saved under `.data/receipts/`. The quota is not reported as a fake $0
API charge. See [Codex automation](https://learn.chatgpt.com/docs/non-interactive-mode) and
[authentication](https://learn.chatgpt.com/docs/auth).

Each job permits at most six model calls by default. Direct API calls allow at most 16,000
output tokens; Codex uses its CLI/model limits and a constrained final schema. There is no
automatic retry. Usage is retained across invalid replies and cancellation. An unknown request
outcome remains unknown and blocks another call to that provider for the same clip. Local
analysis remains available. API prices are estimates; Codex plan usage is shown separately.

Selecting a remote model and starting analysis sends the selected frames to that model's service.
Keys and local runtime data remain outside Git. Qwen is still an evaluation candidate.

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

# Engineering V1 validation

Checked on 2026-10-08 on macOS Apple Silicon. This record concerns software behavior;
it does not establish biomechanical accuracy or improvement in shooting performance.

## Automated checks

- 15 backend tests pass. They cover variable-frame-rate import/copy/time mapping, unavailable
  versus true-zero measurements, insufficient post-release context, comparison context/hand,
  correction history and stale writes, reference invalidation, idempotent request intent,
  cancellation, provider response validation, usage retention, unknown request outcomes,
  and restart without resubmitting a paid request.
- Ruff passes; TypeScript and the Vite production build pass.
- Official model downloads are SHA-256 checked. Pose model: 9,398,198 bytes; YOLOX: 35,858,002 bytes.
- A dependency emits a Starlette/httpx deprecation warning in tests. No test failed.

## Real local-vision and artifact check

Six existing clips were copied from the Workbench run ending `fd8334e6`, preserving the source
video offsets and original frame indices. They contain 364 decoded frames in total. Each clip
completed local vision analysis and produced a written review, JPEG, MP4 and evidence JSON.
MediaPipe pose and OpenCV YOLOX ran on the real frames, with no model API call.

| Clip | Decoded frames | Valid wrist-height frames | Quality flags |
| --- | ---: | ---: | --- |
| Shot 1 | 66 | 51 | none in the initial measured windows |
| Shot 2 | 61 | 38 | estimated shooting side uncertain; track gaps |
| Shot 3 | 55 | 36 | insufficient later context; track gaps |
| Shot 4 | 66 | 50 | none in the initial measured windows |
| Shot 5 | 65 | 47 | insufficient later context |
| Shot 6 | 51 | 39 | insufficient later context |

These counts are visibility checks, not pose accuracy. The automatic release intervals are
candidates. The first clip was reviewed through the UI at frames 39–41 (source 4.967–5.033s),
and the report advanced to revision 1. The shooting-hand uncertainty condition disables
numerical reference comparison until the side is set; other metrics gate their own windows.

All six MP4s were decoded end to end with FFmpeg: 1280×840, 25 FPS, 200 frames, 8 seconds.
Every recorded output-frame reference matched an imported source frame and source timestamp.
The player and report retain actual PTS; unavailable context is clamped to the available source
frame and its actual displayed time is recorded. This is a rendering policy, not reconstructed motion.

## Browser checks

A real Chrome session exercised personal-comparator selection, phase correction, refresh and
persisted revision, English/Chinese switching, frame stepping, Chinese report regeneration,
and a real written-report download. The PNG report and desktop/mobile screenshots were
visually inspected. Movement focus makes the subject legible while maintaining a fixed crop;
pose overlays were checked against the cropped source image. At 390px width, the document
and viewport widths both measured 390px. Startup-related reload errors and an initial favicon
404 occurred during development; the favicon is now embedded in the document.

Private screenshots, frame tracks and reports remain under `.data/`, outside Git. The earlier
committed visual-design example is separately described in `VALIDATION.md`.

## Limits and subsequent validation

The direct Gemini and Astra API adapters were tested with controlled responses, including
invalid evidence, timeout and late cancellation. No live direct-API request was made in these
checks. Transport is ordered JPEG frames, not native video. Astra additionally supports the
Codex transport validated below; Qwen remains unintegrated. No cross-model ranking is claimed.

The default body selector is a largest/continuous visible-person heuristic, not a trained
identity tracker. There is no shooting-specific ground truth, calibrated 3D analysis, universal
pose score, causal miss classifier, training log, or measured Curry motion. Current manual
correction covers the release interval; other phase edits and stability attributes are later work.

M6 needs 30–50 independently labelled clips from multiple sessions/views. M7 needs matched
practice, no-cue and cross-day retests. Those dependencies are separate from this runnable V1.

## Provider and startup update (V0.3)

21 backend tests pass after adding provider-specific receipts and billing, missing-key rejection,
Codex command/environment boundaries, real subprocess JSONL parsing, and child cancellation
with received usage retained. The production frontend build passes. The model selector exposes
Gemini, Astra (Codex), Astra (API), and local vision in both languages; a 390px browser check
shows no horizontal overflow.

The `start.sh` launcher installs/checks dependencies, creates a missing local environment file,
checksums the models, reports model/auth readiness, waits for both services and can open the
browser. `start.command` supplies a macOS double-click entry. `--check`, `--no-open` and repeat
startup were exercised. Existing local Gemini configuration was reused in the ignored `.env`;
credentials and runtime files were checked to remain outside Git.

One **live Codex/Astra call on eight newly generated synthetic stick-figure images** completed
successfully through ChatGPT auth: 16,319 input tokens and 154 output tokens were recorded.
The returned phase interval and observation frame IDs passed the same validation as other
providers. The process emitted one completed turn, with no tool calls. This verifies transport,
structured response and usage capture; it is not evidence of shooting-analysis accuracy.

A proposed live test on the user's private shooting clip was rejected by automatic approval
review because specific authorization to transmit that video to OpenAI was absent. No such
request was submitted. Private-clip validation remains pending explicit user authorization.
Direct Astra API and Gemini calls use controlled-response boundary tests in this update.

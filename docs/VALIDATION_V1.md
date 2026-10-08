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

## Human coaching review update (V0.4)

49 backend tests and 5 frontend interaction tests pass, with the production TypeScript/Vite build.
New coverage includes readable metrics, no-fault/limited-data states, source/frame/rubric validation,
priority and confidence caps, stale model coaching after phase edits, historical-export protection,
reference consistency, bilingual updates and evidence jumps. Finish timing is tested at 20/30/60/120 FPS,
including occlusion, ambiguous hand positions and conservative censored lower bounds.

A real Chrome session checked the local six-clip copy at desktop1440 and mobile390 widths.
The summary, human metrics, source evidence navigation, frame stepping, unsaved correction controls,
slow playback, pose visibility, model selection persistence and reference-sensitive export protection
worked. Three ranked issue cards and expanded reasoning/drills were exercised using an explicitly
marked synthetic UI fixture without a real person's video. Screenshots were captured and viewed;
no horizontal overflow or browser console errors were found in the checked flows. Native browser
200% zoom was not tested.

A local report for the first clip and its personal comparator was regenerated from cached tracks,
with no remote model request. The Markdown, JPEG and MP4 use the same coaching record. New video
exports are 1280×1000, 25 FPS, 200 frames /8 seconds; a full FFmpeg decode passed.

One live Astra/Codex request used only the eight previously generated synthetic stick-figure images
and the new rubric/schema. It returned bilingual coaching plus phase and frame references
(20,601 input tokens,416 output tokens). Initial validation incorrectly classified legitimate frame
numbers in the prose as invented measurement values. That guard was corrected and regression-tested;
the already received response then validated without another remote request. This verifies the
transport and output contract, not coaching accuracy. No private shooting video was sent to a new
model service during this update, and no real coaching issue was fabricated to fill the redesigned UI.

The permanent app instance was upgraded to V0.4 and all six existing reports were rebuilt locally.
All six rebuild jobs succeeded; each report's revision and every movie-frame source reference
were checked, and all six newly rendered videos decoded end to end. The original clips and
phase revisions were preserved. No remote model request was involved in that refresh.

## Unified settings follow-up

All configuration was moved into the top-right Settings drawer: analysis method, shooting
context, imports, personal comparator, playback preferences and language. Workbench import
now says “Import pre-cut shots” and explains that it reads completed Video Event Workbench
exports with original video times. Main review content retains execution/playback actions
and read-only context; configuration selectors appear only in the drawer.

12 frontend interaction tests and the production build pass. Real Chrome checks at1440px and
390px verified language switching, local preference persistence, internal drawer scrolling,
no horizontal overflow, Escape/backdrop closing, focus return and first/last Tab wrapping.
Changing settings generated no non-GET requests. Mocked tests cover Workbench states and
upload-error recovery; no real clip was uploaded or sent to a model for this UI follow-up.

## Review outcomes and pose comparison (V0.5)

The current local records explain the reported empty issue panels: Shots2–6 have accepted
Astra reviews describing visible strengths with no major correction, while Shot2's valid
review was previously suppressed by a local handedness flag. Shot1's latest Gemini request
has no successful review. These cases now have distinct states; cached valid strengths and
summaries are retained with dimension-specific limits.

A synthetic text-only request reproduced a Gemini HTTP400 for the old response_schema
serialization (unsupported additional_properties fields). The same schema sent through
response_json_schema succeeded (21 input tokens,29 output tokens), without any personal
video or image. New receipts capture HTTP rejection codes separately from unknown outcomes.
No historical unknown charge is rewritten as zero, and private analysis is not retried silently.

83 backend tests and19 frontend tests pass, plus Ruff and the production build. New tests cover
review outcomes, partial uncertainty, optional rubric coverage, pose adaptation/provenance,
phase and scale registration, visibility/view gates, frame-range clipping, known HTTP rejection,
and explicit unknown-request retry authorization before queue creation.

Real Chrome checks on1440px desktop and390px mobile inspected teaching and personal overlays,
phase jumps, readable differences, Shot2's preserved review with a separate overlay limitation,
and the failure state. Teaching mode draws only the demonstrated shooting arm; personal mode
uses the selected real shot. Screenshots were captured and viewed. No model POST/retry was
made during this UI check. Newly drawn reference geometry is a visual teaching aid and is not
validated motion-capture ground truth or a technical-fault threshold.

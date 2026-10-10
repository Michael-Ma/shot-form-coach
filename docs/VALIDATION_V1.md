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

## Full-video lifecycle and failure diagnosis (V0.6)

The product flow is now video library → clip management → individual review. Importing a
recording or editing boundaries does not queue a remote evaluation. Analysis is an explicit
action on selected clips. Existing short clips are grouped by their import source.

**111 backend tests and 34 frontend tests pass**, together with Ruff, TypeScript/Vite production
build and an offline lockfile check. New coverage includes long-video upload/preview, HTTP range
playback, nonzero-origin variable-frame-rate cutting, stale lifecycle forms, reversible trash,
active-job guards, metadata edits retaining paid coaching, interrupted-job recovery, scan failure
with manual fallback, cancellation, and explicit retry after an unknown network outcome. A long
synthetic motion sequence also verifies that later candidates are not silently capped at 200.
The pre-existing Starlette/httpx deprecation warning remains non-failing.

A separate local snapshot of the 13 existing clips was used for browser verification. In Chrome,
the 54.838-second original recording was uploaded through the new primary entry, prepared for
playback, and used to save two manual clips. One clip was trimmed into a new identity, another
was moved to trash and restored. A locally proposed range was previewed and saved as a third
clip. Selecting only one clip produced one successful local-analysis job with no provider
receipts. Its current Chinese report was regenerated locally, downloaded through the browser,
and all four artifact types existed; the MP4 decoded end to end. The return path to the library
and the real recent failure state were exercised.
The scan was also cancelled through the visible processing control; all three saved QA clips
remained available and the UI offered manual marking and another explicit scan.

Desktop (1440px) and narrow mobile (390px) captures were inspected. Review moved the scan
action into the first visible source-video area and removed a mobile sticky analysis bar that
overlapped clip controls. The checked layouts have no horizontal overflow. Source labels,
Chinese/English feedback, scoped processing/error states, and the boundary between global
settings and a particular clip's comparison were checked. These are engineering and heuristic
walkthroughs, not usability research with independent users; native 200% browser zoom was not tested.

The local scan decoded 1,645 source frames, sampled 275 poses and proposed five wrist-rise
intervals in approximately 12 seconds. It did not propose an interval for the earlier imported
shot around source 13–15 seconds. This confirms the need for manual additions; it does not
establish recall, precision, or complete coverage of shooting events. Sampling/processing
coverage is recorded separately from event detection. Proposals are explicitly unconfirmed.

### The two most recent visual-review failures

The two requests at approximately 22:18 and 22:19 on October 8 (America/Los_Angeles) both
logged `stream disconnected before completion: error sending request`. Both exited with code 1,
without a completed turn, review text, or usage. The successful six-clip batch and these failures
used the same Codex CLI version, 0.162.0-alpha.2. Failed inputs contained 66 and 52 frames,
within the earlier successful 51–66-frame range. The output schema had changed, but the recorded
errors contain no explicit schema rejection. A specific underlying network/provider cause
cannot be established from these logs.

One live synthetic text-only request using the production command and authentication succeeded
in 4.263 seconds, returning a valid minimal JSON response (15,301 input tokens, 15 output tokens).
This verifies current basic connectivity, not a full image request or shooting-review quality.
No private footage was sent for this diagnostic check, and the failed private requests were not retried.

New receipts retain safe specific diagnoses and request context. The two older failures are
classified read-only from their local event logs; receipt history and unknown billing remain
unchanged. The UI now says that the visual-model connection was interrupted, retains local
measurements, and offers the existing explicit single-clip retry path. Coaching version v3
prevents old generic-failure exports being presented as the current result.

The installed application now runs at version 0.6.0 on its existing local address. A before/after
comparison confirmed all 13 asset identities, source hashes, frame mappings, phase revisions
and model-review records were preserved. Seven analyzed clips' reports were rebuilt solely
from cached data; all jobs succeeded, every report matched its clip revision and v3 coaching,
and all seven exported videos passed full decoding. The installed browser view reported no
console errors or warnings.

## Duplicate-pose recovery and Codex transport diagnostics (V0.6.1)

148 backend tests pass, with Ruff and the TypeScript/Vite production build. New tests cover
duplicate versus distinct bodies, conflicting limbs, non-finite coordinates, identity changes,
short and long gaps, normal jump continuity, invisible-wrist false positives, bounded trace
retention, and persistence through the worker. Detailed scan evidence is available at the
video's `scan_diagnostics_url`; ordinary polled video responses omit the large decision trace
and anomaly-event arrays. The endpoint labels retained evidence as the last successful scan
and also reports the current scan status/error.

The original 54.838-second source was decoded and scanned from frame zero using the same
MediaPipe model and 5 Hz sampling. V2 returns peaks at **5.000000, 14.401667, 24.401667,
33.803333, 43.005000 and 52.005000 seconds**. All five V1 peaks are unchanged; only the missing
shot was added. At 14.401667 seconds the trace records two raw poses, one distinct pose after
geometry checks, `duplicate_pose_merged`, and an updated pending peak. The pair shared nine
reliable support joints; eight were within the configured agreement threshold. These are
geometric compatibility checks, not verified identity or a calibrated probability of duplication.

Whole-video validation caught and corrected two intermediate regressions before release:
ordinary jumping was initially rejected by a restrictive movement gate, and preserving an
unqualified low-wrist observation through missing data introduced an extra candidate. The
final implementation allows ordinary adjacent-frame movement separately from stricter
reacquisition after a gap. It retains V1's conservative reset of unqualified missing-wrist
history while preserving already qualified motion for review. True ambiguity, long gaps and
identity discontinuity do not create a new low-to-high action across the gap.

A second run through the actual worker completed in about 13.5 seconds, persisted the six
candidates and the 14.40-second anomaly, and preserved all 17 assets in the isolated QA copy
(including its previously trashed version). The results remain unconfirmed candidates; this
single-source regression does not establish general recall or precision.

### Codex investigation and controlled reproduction

The two historical failures were not the app's 1,200-second deadline: their receipts record
`codex_call_failed`, and the final error-file times were approximately 2.5 and 2.3 seconds after
call registration. These are filesystem timing estimates, not exact network latency. One failed
66-frame input was byte-for-byte the same ordered image set used in two earlier successful
calls (18,810,307 JPEG bytes). Historical logs do not contain an HTTP status, underlying exception
chain or transport timeout/connect flags, so a specific historical network cause remains unknown.

Current Codex doctor checks found the configured provider reachable over HTTP and an available
WebSocket handshake. These reachability checks alone are not a model inference test. The
production runner still uses its configured HTTP transport, with zero automatic retries.

**One live controlled inference** used 66 newly generated synthetic calibration JPEGs totaling
18,634,576 bytes, the same requested Astra model and CLI version, and exactly the same 4,061-byte
output schema as the failed calls. The targeted diagnostic log captured a Responses HTTP 200 at
11.570 seconds, model output at 32.596 seconds, completion at 32.636 seconds, and process exit 0
at 33.171 seconds. Usage was 95,221 input tokens and 739 output tokens. The result passed both
the structured reply and coaching-evidence validation. This establishes that the current full
image/schema route works; it does not reconstruct the historical intermittent failure. No
private footage or failed private request was sent again.

New per-call `diagnostics.json`, `timeline.jsonl` and sanitized `stderr.log` record terminal
timing, input size, schema/config identity and typed transport evidence when supplied. Local
CLI thread IDs are kept separate from remote response/request IDs. Only content-free allowed
fields from targeted debug output reach the new logs. Tests exercise secret/header/body
filtering, log size caps, request attribution, timeout false positives, cause specificity,
pipe backpressure, cancellation with blocked input, timeout after output closes and spawn
failure. Raw debug logs and diagnostics are not committed to Git.

The installed local app was upgraded to 0.6.1 and targeted CLI diagnostics were enabled for
future user-initiated analyses. The original 13 clips, source hashes, frame mappings, phase
revisions, model-review records and saved reports matched the pre-update snapshot exactly.
No private analysis was resubmitted during installation.

## Independent video import (V0.6.2)

The homepage now has one primary video-import entry. The external Workbench importer,
startup request for its completed runs, backend routes and environment configuration were
removed. Existing saved assets remain local collections with generic labels; their original
timelines and reviews are retained. No external project's directory is read by the application.

148 backend tests and 34 frontend tests pass, with Ruff, TypeScript/Vite production build
and the lockfile check. The updated interface regression checks both English and Chinese,
one import button, no Workbench text and no external-project import requests.

## Detailed assessment coverage and focused inputs (V0.7)

An inspected cached review had an empty raw model issue list, four aligned coarse dimensions
and one uncertain hand dimension. The UI had therefore presented a no-priority-issue result;
no supported issues had been removed by the display filter. That result did not establish that
setup, ball route, arm alignment or release timing had been examined in detail.

The rubric now has nine dimensions with explicit review questions. Current remote replies must
account for all nine; missing/unclear dimensions cannot yield a whole-form no-issue conclusion.
The visible summary reports assessment coverage and identifies saved older evaluations. Original
model prose remains original; missing dimensions are labelled unreviewed, never retrospectively
generated. Review provenance includes rubric and image-input-plan versions.

Model inputs combine full context and fixed body crops decoded from the original pixels, under
the existing total image cap. The inspected longer clip prepared 12 full-scene and 68 body views
(75 distinct source frames), about 12.2 MB of JPEG data. View and crop metadata preserve source
frame/time identities. Crops do not invent detail or make unseen fingers/forces observable.

A local timing bug was also reproduced: the global minimum hip position belonged to earlier
preparation rather than the final shooting load. The revised local-window derivation changes
that example from about 2.92 seconds to about 0.28 seconds. Manual phase corrections remain
authoritative; boundary maxima and insufficient rise evidence stay unavailable.

153 backend tests and 35 frontend tests pass, with Ruff and the production build. New tests
cover incomplete versus complete assessments, mandatory current rubric coverage, preserved
old reviews, preparation versus final load, manual phase preservation, native-resolution crops,
CFR/VFR frame/time identity and total image budgets. Chrome desktop/mobile inspection of the
cached example confirmed the 4/9 coverage summary, one unclear dimension, four unreviewed
dimensions and corrected timing, with no horizontal overflow.

No new model assessment of private footage has been performed for this update. A synthetic
text-only protocol probe was blocked before execution by automatic approval review because
export of the new prompt and rubric had not been explicitly authorized. A new private-clip
comparison remains conditional on explicit user authorization. Local checks verify software
behavior; they do not establish improved coaching sensitivity or accuracy.

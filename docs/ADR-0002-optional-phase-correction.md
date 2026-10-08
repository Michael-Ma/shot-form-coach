# ADR 0002: Optional correction of release and movement phases

Status: accepted by the user on 2026-10-07. This records the product decision;
the automatic phase analysis and correction UI still need implementation.

## Decision

The default workflow analyzes a clip automatically and produces an appropriately qualified
report. The user can optionally correct the release interval or another key phase with one
or two clicks. There is no mandatory per-shot approval step.

For release, the UI offers the last frame with visible ball-hand contact and the first frame
with clear separation. A single-frame selection remains a proposed anchor with frame-rate
uncertainty; it does not become an exact physical instant. Hidden contact can be marked unknown.

Corrections preserve the original model proposal and create a new phase revision with the
changed fields, actor, evidence frames, and source timestamps. Unedited proposals are not
relabeled as human-confirmed annotations.

## Recompute behavior

Reuse decoded frames and unchanged pose/ball tracks. Recompute the affected phase alignment,
measurements, findings, and render outputs. Retain previous versions for comparison, while
making the current report's phase revision explicit. Received model usage remains attached
to its original attempt, and unknown remote requests are not automatically resubmitted.

## Interface

- A release marker and phase ranges on the synchronized timeline.
- An optional frame-level correction control near the video.
- Clear indicators for model-proposed, user-corrected, and explicitly confirmed phases.
- Specific missing-evidence messages when contact or another phase cannot be seen.

Corrections form an auditable local annotation set for review and evaluation. They are timing
labels, not labels proving that a player's shooting technique is correct.

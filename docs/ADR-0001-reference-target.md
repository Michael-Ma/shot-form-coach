# ADR 0001: Separate reference motion from an individual training target

Status: proposed for the first implementation.

## Context

A Stephen Curry reference can explain a shooting principle. Differences in camera view,
shot distance, shot type, body proportions, and personal coordination mean that a raw
pose difference is not automatically a mistake. A made shot does not validate every
part of its technique, and a missed shot does not identify one causal error.

## Decision

Keep three distinct records:

1. **Reference observation:** what a sourced demonstration or personal comparator shows.
2. **Measurement/difference:** what is observable under stated camera and phase conditions.
3. **Training target:** a bounded hypothesis and practice cue that can be tested in a later session.

Use phase anchors to align motion. Preserve original phase durations so alignment does not
hide a pause or timing difference. Constrained time warping may assist visualization later;
it cannot replace the timing comparison. Do not compute cross-view errors from raw 2D
pixel distances or treat estimated depth as calibrated motion capture.

The first example uses a personal comparator plus an original schematic based on published
teaching. Neither is labeled as measured Curry motion or a universally correct full-body pose.

## Consequences

Findings remain useful when some measurements are unavailable. The UI can show a difference
without issuing a diagnosis, and every image/video label can be traced to its source.
Rules and targets require validation separately from pose-detection accuracy.

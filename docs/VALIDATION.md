# Design example validation

Date: 2026-10-07.

## What was inspected

The existing native-video Workbench run contains six matched exports at 1920 by 1080
pixels and approximately 30 FPS, with durations of 1.70 to 2.20 seconds. Forty-two
source-mapped frames were inspected across the six exports. Denser windows around
the first two releases were inspected to propose approximate phase anchors.

The release intervals and regions in `examples/review-spec.json` are visual-review
annotations authored during this design exercise. They have not been adjudicated by
an independent coach. No automatic pose measurements or new paid model calls were made.

## Output checks

- The renderer decodes existing clips with one image per decoded frame and checks the
  image count against the ffprobe frame-timestamp index.
- Every output frame has a record linking it to both input clip frame indices and source times.
- Source clips are content-hashed. Source times remain inside the respective exported ranges.
- The example uses approximate release alignment and 0.4x playback. It includes an initial
  one-second hold and a final 3.5-second hold, for eight seconds total at 25 FPS.
- The still and video identify the third panel as an original teaching schematic and identify
  coach review as pending. The second shot is a comparator for one attribute, not an ideal pose.
- The still and representative video frames were visually reviewed for legibility and preserved
  source content; the MP4 was decoded end to end. JSON files, Python syntax, and lint were checked.

## Not established by this example

Automatic phase accuracy, joint-angle accuracy, coach agreement, false-positive rate,
shot success, a causal error diagnosis, or improved shooting performance. Those require
the separate validation stages described in the design.

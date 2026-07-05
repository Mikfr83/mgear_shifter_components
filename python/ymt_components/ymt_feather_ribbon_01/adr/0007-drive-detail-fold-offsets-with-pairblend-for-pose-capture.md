# ADR-0007: Drive Detail Fold Offsets With PairBlend For Pose Capture

Status: Proposed
Date: 2026-07-05
Owner: ymtshiftercomponents maintainers
Supersedes: ADR-0006 (fold offset driver mechanism only)
Superseded by: none

## Context

ADR-0006 drives each col-0 `{detail}_fold_npo` with two multiply nodes:
`fold * yaw` into rotateY and `fold * tilt` into rotateX, with zero-valued channels
skipped. The parent wing now supports capturing the posed rig as the new fold target
(parent ADR-0004 "Capture Rig Fold Pose Into Baked Fold Targets"). Detail controls
carry arbitrary rotations, and a two-channel multiply rig cannot store a captured
arbitrary rotation per feather root.

## Decision

- Replace the per-feather multiply pair with one `pairBlend` node (quaternion
  interpolation) per col-0 fold npo: `inRotate2` initialized to
  (tilt, yaw, 0) XYZ degrees from the per-row `foldTiltSteps`/`foldFanClose`
  parameters, `weight` driven by the parent fold plug, `outRotate` driving
  `fold_npo.rotate`.
- Create the pairBlend for every col-0 fold npo when fold is wired, including
  feathers whose initial angles are zero, so every feather root is capturable.
- Add `control.py` with a script-invoked `capture_fold_pose(component_root)`:
  for each fold pairBlend, the new `inRotate2` is the rotation of the col-0 detail
  control composed with the current `fold_npo.rotate` (matrix composition, rotate
  order respected, child rotation first in Maya's row-vector convention); the col-0
  detail control rotation is then zeroed. The function never touches the fold
  attribute — the parent wing owns it and writes it once after cascading captures.
- Guide parameters remain the build-time defaults; captured rotations are
  rig-scene-local and a rebuild restores the parametric fan/tilt pose, consistent
  with parent ADR-0004.

## Considered Options

1. Keep multiply nodes and capture only the X/Y euler components of the control
   - Pros: no hardware change.
   - Cons: silently drops the Z component and misorders composed rotations; lossy
     capture was rejected.
2. Exclude feathers from capture (arm only)
   - Pros: nothing to change here.
   - Cons: folded silhouettes are mostly feather silhouettes; rejected.
3. PairBlend per feather root with full-rotation capture (chosen)
   - Pros: exact capture; same driver pattern as the parent wing fold offsets;
     ~tens of pairBlend nodes replacing pairs of multiply nodes is cost-neutral.
   - Cons: node graph differs from ADR-0006's original wiring; zero-angle feathers
     now carry a driver node too.

## Consequences

The fold offset layer keeps its position and additivity from ADR-0006 (between
`chain_npo` and `aim_npo`, no feedback into rivet/aim layers); only the driver of
`fold_npo.rotate` changes. Detail controls on col > 0 are not part of capture and
keep their animation. Capture is idempotent when repeated without repositioning.

Maya runtime validation is required for: quaternion interpolation of composed
(tilt + yaw + captured) rotations across the fold range, and capture round-trip
stability on mirrored (right-side) components.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- captured feather poses need to survive rebuilds (serialize per-feather overrides
  into a guide setting or build-step data).
- per-feather fold weighting (not just rotation) becomes necessary.

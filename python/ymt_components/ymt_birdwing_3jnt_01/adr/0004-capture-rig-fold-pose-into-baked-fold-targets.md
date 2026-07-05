# ADR-0004: Capture Rig Fold Pose Into Baked Fold Targets

Status: Proposed
Date: 2026-07-05
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

## Context

ADR-0003 authors the fold target pose on the guide. After a rig is built, art-directing
the folded silhouette through the guide is slow: edit locators, rebuild, re-evaluate.
Riggers want to pose the built rig with the existing FK and detail controls and adopt
that pose as the new fold target without a rebuild.

The fold targets live in the rig as baked local XYZ rotations on the
`fk{i}_fold_pb` pairBlend `inRotate2` plugs. They are independent per segment at
runtime (the build-time accumulation from ADR-0003 only converts the guide world pose
into locals once), so a capture can be computed segment-locally.

## Decision

- `control.py` gains a script-invoked function `capture_fold_pose(component_root,
  include_feathers=True)`. No UI; the argument is the component root node (namespace
  aware). Rigs built without fold locators raise a clear error.
- Capture semantics: the currently visible pose becomes the new `fold = 1` target.
  For each FK segment i in 0..2: new local delta = rotation of `fk{i}_ctl.rotate`
  composed with rotation of `fk{i}_fold_npo.rotate` (matrix composition, respecting
  each node's rotate order; child rotation applied first in Maya's row-vector
  convention), written to `fk{i}_fold_pb.inRotate2` as XYZ degrees. The FK control
  rotations are then zeroed, and the `fold` anim attribute is set to 1 as the final
  step, after all reads and writes across the wing and its feathers.
- The hand segment (index 3) has no FK control (`fk_ref` is rigid under `fk2_ctl`),
  so its delta is not capturable from the rig and stays unchanged. Hand tip fold
  adjustments remain guide-only.
- The function warns instead of failing when: the effective blend (blend attribute
  multiplied by the reverse of the `foldPull_clamp` output) indicates visible IK
  influence, or FK control translations are non-zero (translation cannot be captured
  into the rotation-only fold layer and is left on the controls).
- `include_feathers=True` cascades into child `ymt_feather_ribbon_01` components
  (their capture is defined in that component's ADR-0007) before the single final
  fold-attribute write.
- Captured targets are rig-scene-local by decision. A rebuild restores the
  guide-authored fold pose; persisting captures back to the guide is out of scope.
- The whole operation runs in one undo chunk.

## Considered Options

1. Guide round-trip only (no rig capture)
   - Pros: single source of truth.
   - Cons: slow iteration; rejected by workflow requirements.
2. Capture also writes the guide fold locators
   - Pros: survives rebuilds.
   - Cons: rig scenes usually do not contain the guide; inverse-solving locator
     positions duplicates build math. Deferred until the workflow demands it.
3. Rig-local capture of the currently visible pose (chosen)
   - Pros: instant iteration; segment-local math; no build dependency.
   - Cons: lost on rebuild; documented and accepted.
4. Require `fold = 1` before capture
   - Pros: prevents surprising pose jumps at partial fold.
   - Cons: rejected as inflexible; instead, capture-at-any-fold adopts the visible
     pose as the full-fold target and running at `fold = 1` is the documented
     recommendation.

## Consequences

Capturing at `fold < 1` redefines the visible pose as the `fold = 1` pose, so the rig
snaps when the fold attribute is raised to 1 by the tool; running at `fold = 1` avoids
any visible change. IK/FK match tooling is unaffected (it reads the raw `blend`).
Setting the fold attribute fails with a warning when the attribute is keyed or locked.

Maya runtime validation is required for: capture round-trip stability (capture, zero,
re-capture must be idempotent), rotate-order handling on FK controls, and the cascade
ordering with feather captures.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- captures need to survive rebuilds (add guide write-back or a serialized override
  re-applied by a build step).
- the hand tip segment needs rig-side adjustment.
- animators need a partial-fold capture that preserves the current fold value.

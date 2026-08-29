# ADR-0003: Two-Pass Collision - Corrective Surface Deformer After Ring Shaping

Status: Proposed
Date: 2026-08-28
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

## Context

ADR-0002 revision 3 shapes the skirt by skinning the collider-generated
surface with ring controllers. Ring edits (and any future surface-stage
effect, e.g. the deferred wave/oscillate feature) compose AFTER the
`skirtBellCollider` node's internal collision resolution, so they can push the
surface back into the legs.

The rigger requested a two-pass architecture: collider -> ring shaping ->
a second collision pass that determines the final shape, designed as the
foundation that later surface-stage effects (wave) also feed through. The
wave feature itself stays out of scope (it needs separate design work for
anime-style expression); this ADR only establishes the composition rule.

`skirtBellCollider` is a generator (no geometry input), so it cannot be
applied twice. The colliders plugin is now maintained in the rigger's fork at
`github.com/yamahigashi/colliders` (checked out at
`/mnt/d/Projects/Pipeline/rez-packages/third/github.com/yamahigashi/colliders/2.1.0/colliders`),
which builds the deployed `colliders.mll`; new C++ work happens there. The
fork's solver sources provide `createRingMatrix` (leg collision ring frames
from hip matrices, ring axis enums, and `ringScale`) and the per-level bell
solver; the latter is level-ring-centric and not reusable for arbitrary
geometry, so the second pass defines its own per-point primitive sharing the
same ring FRAMES.

## Decision

### New plugin node: `skirtCollideDeformer` (in the yamahigashi colliders fork)

An `MPxDeformerNode` that pushes the deformed geometry's points out of the
leg collision volumes. It is a CORRECTIVE pass: it does not generate shape,
it only resolves penetration of whatever geometry it receives.

- Attributes (matching `skirtBellCollider` semantics where names coincide):
  - `leftHipMatrix`, `leftKneeMatrix`, `leftHeelMatrix`, `rightHipMatrix`,
    `rightKneeMatrix`, `rightHeelMatrix` (matrix inputs, world matrices).
  - `skirtType` enum Short/Long (Long adds the knee-to-heel rings, as pass 1).
  - `ringScale` (double3) and `leftRingAxis` / `rightRingAxis` enums, same
    meaning as the generator node.
  - `collision` (0..2, default 1): blend factor of the correction; values
    above 1 overdrive the push to compensate for NURBS CV dilution (moving a
    CV to the boundary leaves the surface, a convex combination of CVs,
    slightly inside).
  - `falloff` (0..1, default 0.2): C1 soft-clamp band, RELATIVE to the local
    ring radius. Points deeper than the band always reach the boundary
    (never under-resolved); points within +-band of the boundary follow the
    hermite blend r' = R + (r - R + band)^2 / (4 band), producing a smooth
    bulge on both sides of the contact instead of a crease.
  - Standard deformer `envelope`.
- Ring volumes: exactly the ring frames pass 1 uses - built with
  `createRingMatrix` (moved from `skirtBellCollider.cpp` into a shared
  header/translation unit so both nodes use one implementation) with
  `thighScale = (ringScale.x, L_thigh * ringScale.y, ringScale.z)` for
  hip-to-knee and, for Long, the heel-length variants
  (`hipToHeel`, `hipToKneeExtended`) as in the generator's `compute`.
- Per-point primitive (per ring volume, in ring local space
  `p_local = p * ringMatrixInverse`): the collision volume is the CYLINDER
  unit radius over y IN (0, 1 + endFade) - the ring frame spans hip (y=0)
  to its aim target (y=1). The y<0 mirrored lobe sits above the hip and
  never collides (it grabbed the waist rows in testing), and the earlier
  spherical taper (radius -> 0 at y=1) left the hem uncorrected exactly
  where ring influence peaks, hence the cylinder. Both axial ends FADE
  smoothly (`endFade` attribute, 0..0.5, default 0.1, smoothstep): a hard
  y gate popped the correction on and off as CVs crossed the ring ends
  (the contact-onset jitter seen in Maya). The far end fades over
  (1, 1 + endFade] so the hem at y <= 1 keeps full coverage.
- Push DIRECTION comes from the skirt cone, not from the point: the deformer
  takes a `bellMatrix` input (the component connects `waistRef` worldMatrix;
  local Y is the cone axis) and pushes along the point's bell-radial
  direction projected into the ring XZ plane (falling back to the point's
  own leg-radial direction only when that projection degenerates).
- Push TARGET is the CHORD EXIT, not the full radius: decompose the ring
  XZ offset into s (along the push direction) and q (perpendicular);
  the boundary along the push line is s_boundary = sqrt(R^2 - q^2)
  (0 when |q| >= R). The signed extent s feeds the C1 soft clamp under
  `falloff` toward s_boundary, so a tunneled point (negative s) returns
  to the NEAR-side chord exit. The earlier fixed target s = R shoved
  grazing contacts (|q| near R) a full radius sideways and hurled
  near-outside points placed perpendicular to the push direction - the
  deep-penetration misdirection and boundary rattling seen in Maya.
  Points outside the radius (R < r < R + falloff) get the contact bulge
  scaled by a smoothstep radial fade that reaches 0 at the gate, so the
  band edge never steps.
  Local y is preserved (the skirt slides outward, not down) and the
  displacement is scaled by
  `collision * envelope * deformer weight * axialFade * radialFade`.
  Multiple overlapping rings apply
  sequentially in a fixed order (left rings then right rings, hip-to-knee
  before heel variants); the sequential result is order-dependent only in
  the overlap between legs, accepted for a corrective pass.
  Degenerate ring matrices (near-zero determinant) are skipped for that
  frame rather than producing NaNs.
- Registration in `main.cpp` with a new type id following the fork's id
  scheme; no draw override (the deformer has no viewport drawing of its
  own).

### Component-side chain (ymt_skirt_01)

- Deformation chain becomes:
  `skirtBellCollider` (generate + first collision) -> `rebuildSurface` ->
  `ringSkin_skc` (ADR-0002) -> [future wave slot] -> `skirtCollideDeformer`
  (final correction) -> surface shape -> cell rivets.
  The corrective deformer is added LAST so every surface-stage effect feeds
  through it; that is the wave foundation this ADR establishes.
- The deformer is created after the ring skinning, on the same surface; its
  six leg matrices connect from the same internal reference transforms
  (ADR-0001), `skirtType`/`ringScale`/ring axis values are set to the same
  values as pass 1 (ringScale through the same root-scale-wired multiplies:
  connect the pass-1 `ringScale` node outputs to the deformer's `ringScale`
  children).
- Sampling-stage rules (cycle safety, unchanged from ADR-0002): ring anchors
  sample the PRE-ring-skin rebuild output; cell rivets read the shape's
  final `worldSpace`, which now carries the corrective pass. The deformer
  depends on the ring skin output and nothing samples the deformer from the
  ring layer, so the graph stays acyclic.
- Animator attributes on the ui host: `postCollision` (0..2, default 1.0)
  and `postFalloff` (0..1, default 0.2), connected to the deformer's
  `collision`/`falloff`. Setting `postCollision` to 0 disables the pass.
- Guide parameter `postCollision` (bool, default True) gates the whole
  feature at build time. When True and the loaded colliders plugin does not
  register `skirtCollideDeformer` (older mll), the build raises with a clear
  message (no silent skip); when False the component builds exactly as
  ADR-0002 revision 3.
- `VERSION` bumps to `[1, 4, 0]` in both `__init__.py` and `guide.py`.
- Surface density lever (added after Maya testing, component 1.6.0): guide
  params `rebuildSpansU` (0 = keep the collider's own circumference CVs;
  >0 rebuilds U too) and `rebuildSpansV` (default 4) control the rebuilt
  surface the collide/wave passes push. Coarse CVs make the corrective
  push read as faceting between CVs; densifying is the remedy when the
  chord-exit math alone is not smooth enough. All downstream stages (ring
  skin weights, anchors, calibration, rivets, wave) are per-CV/parameter
  procedural and adapt to any density.

## Considered Options

1. Apply `skirtBellCollider` twice
   - Impossible: the node is a generator with no geometry input.
2. Per-cell push-out in the rig graph (nodes or expression), no plugin change
   - Pros: no plugin fork dependency.
   - Cons: heavy per-cell node networks, corrects rivets instead of the
     surface (orientation and continuity break - the same class of mistake
     ADR-0002 revisions 1-2 made), and gives the wave feature no foundation.
3. Corrective `MPxDeformerNode` in the fork, sharing ring frames (chosen)
   - Pros: one cheap node, corrects the surface itself so rivet positions
     AND orientations stay coherent, composes with any future surface-stage
     effect, reuses the exact collision volumes of pass 1.
   - Cons: fork maintenance and per-Maya-version rebuilds (already the
     rigger's workflow); the per-point primitive is a simplification of the
     generator's level-ring solver (adequate for a corrective pass).

## Consequences

Ring shaping (and later wave motion) can no longer push the skirt through
the legs while `postCollision` is up. The correction is surface-level, so
cells keep coherent frames. FK cell controls remain downstream of the
rivets and are NOT corrected (manual layer stays manual). The plugin fork
gains a second registered node; deployed `colliders.mll` builds must include
it before the component's `postCollision` gate can be enabled on a given
Maya version. Maya runtime validation (deformer chain order, penetration
behavior, performance on 7x5-CV-scale surfaces) is required.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- the wave ADR lands (its output must insert before the corrective pass;
  if it needs post-correction effects, this ADR's chain order needs a new
  decision).
- the sequential multi-ring push-out shows visible order artifacts between
  the legs (switch to largest-penetration-wins or iterative relaxation).
- the corrective pass needs to also affect the FK/manual layer.
- per-point ellipsoid volumes prove too coarse against the generator's
  level-ring behavior (revisit sharing the full solver).

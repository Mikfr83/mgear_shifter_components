# ADR-0002: Ring Shaping Controllers at Knee and Ankle Stations

Status: Proposed
Date: 2026-08-28 (revision 3)
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

Revision history:

- Revision 1: rigid band attachment via per-cell matrix deltas (Codex + GLM
  review, Grok adjudication; artifacts under
  `docs/reference/skirt_design_review/adr2_*`). Rejected in Maya testing.
- Revision 2: bend-chain deformer via anchor-frame deltas, partial-blend
  products, and offsetParentMatrix (single Codex math check). Rejected in
  Maya testing: layering matrix deltas ON TOP of the surface-following npos
  cannot change cell orientation the way deforming geometry does, ankle
  follow was wrong, and row-0 orientation stayed frozen.
- Revision 3 (this text): the rigger's own proposal - rings deform the
  collider surface itself; cells keep following the surface. Feel-iteration
  mode: no external design review this round (rigger agreement), orchestrator
  verification only.

## Context

ADR-0001 builds `ymt_skirt_01` cells as npos riveted to the rebuilt collider
surface with `pointOnSurfaceInfo` frames (position + normal + tangents), an
FK control per cell, and bind joints. Riggers need band-level shaping - sway,
twist, flare - from ring controllers at the knee and ankle stations.

Two attempts that applied shaping AFTER the surface-following layer failed in
testing because cell orientation comes from the surface frame: only deforming
the surface itself makes positions AND orientations respond coherently (a
laterally moved band slants the surface between fixed and moved regions, and
the slant reorients every riveted cell, including the top row whose position
barely moves).

Terms from ADR-0001: cone axis `a`, waist origin, axial projection `A`, hem
projection `A_hem`, stations `s_knee = min(d_knee, A_hem)` and
`s_ankle = min(d_heel, A_hem)` with the 5% single-ring collapse
(`s_single = min(d_heel, A_hem)`), station radius interpolation with endpoint
clamping, the bell frame, `waistRef`, and the rebuilt collider surface shape.

## Decision

Rings deform the rebuilt collider surface through a skinCluster; the per-cell
rivet/FK/joint chain is untouched by this ADR.

### Controllers and influence joints

- Ring controllers `ringKnee_ctl` / `ringAnkle_ctl`: circle icon, IK color,
  placed at their stations, radius = station cone radius x 1.1, all nine TRS
  channels keyable. Each control sits under an ANCHOR transform inside the
  visible `getName("ringCtls")` group. There is no follow child and no chain
  semantics: the ankle ring does NOT follow the knee ring; the surface blends
  between them.
- Anchor follow (rings ride the deformed skirt, position AND orientation):
  eight `pointOnSurfaceInfo` samples around U at the station's V are taken
  from the PRE-ring-skin data (`rebuildSurface.outputSurface`; the surface
  transform is identity so object space equals world space). Sampling the
  final skinned shape is prohibited: it would cycle
  (ring edit -> skin -> anchor -> bindPreMatrix). The anchor translation is
  the sample average (the level center); the anchor orientation is the level
  frame built from the two sampled diameters `d1 = S0 - S4` and
  `d2 = S2 - S6`: Y = normalize(d2 x d1) (the band plane normal; cross input
  order is fixed once at build so the rest Y points hem-ward, a deterministic
  measurement), X = normalize(d1) (orthogonal to Y by construction),
  Z = X x Y. A degenerate rest frame raises. The band tilting or swinging
  therefore tilts the ring gizmo with it, and ring edits (including Y-twist)
  are interpreted in the tilted band frame through the bindPreMatrix
  conjugation. The bindPreMatrix relative-skinning contract below cancels ALL
  anchor follow motion from the skin input, whatever its source, so
  surface-follow does not double-transform. The ring control's build frame is
  the anchor's evaluated frame (not the ideal axis station), keeping its
  local matrix exactly identity at rest. The waist influence anchor stays
  parent-constrained to `waistRef` (its level center is the bell pivot
  itself).
- Hidden influence joints: `getName("ringWaist_jnt")` parented under a
  waist anchor at the waist station; `getName("ringKnee_jnt")` /
  `getName("ringAnkle_jnt")` parented under their ring CONTROL with identity
  local TRS, so each joint's world transform equals its control's. Joints
  are hidden and never keyed directly.
- Single-ring build: no ankle control and no ankle joint; the surviving
  knee-named ring sits at `s_single`.
- The build asserts each ring control's local matrix (and pivots, pivot
  translates, shear, rotateAxis) is identity at the end of `addObjects`,
  raising otherwise.

### Surface skinning

- After the rebuild network and after the rest UV calibration (which runs on
  the untouched rest surface), the rebuilt surface shape receives a
  skinCluster: classic linear (skinMethod 0), weight normalization on,
  influences [ringWaist_jnt, ringKnee_jnt, ringAnkle_jnt] (ankle omitted in
  single-ring builds). Node name `getName("ringSkin_skc")`.
- Relative skinning against the follow motion: every influence's
  `bindPreMatrix[i]` is LIVE-CONNECTED to its anchor's
  `worldInverseMatrix[0]` (the anchor is the influence's ring-edit-free
  neutral frame). The per-influence skin matrix is therefore
  `anchorWorldInverse * jointWorld` = the ring control's local edit
  conjugated at the live anchor frame - identity whenever the ring is
  untouched. Without this, the influences' waistRef follow would re-apply
  motion the collider output already contains, double-transforming the
  surface under waist animation.
- Weights are baked per surface CV from the CV's rest axial projection
  `A_cv` (rest CV world position projected onto the cone axis from the
  waist), classic three-influence hats:
  - Two-ring: `w_ankle(A)` = 0 for `A <= s_knee`, linear on
    `(s_knee, s_ankle)`, 1 for `A >= s_ankle`;
    `w_knee(A)` = `clamp(A / s_knee, 0, 1) * (1 - w_ankle(A))`;
    `w_waist = 1 - w_knee - w_ankle`.
  - Single-ring: `w_knee(A) = clamp(A / s_single, 0, 1)`,
    `w_waist = 1 - w_knee`.
  - Weights sum to 1 by construction; falloff is linear in this version and
    is the primary feel-tuning knob (smoothstep is the expected first
    adjustment; weights are also hand-paintable in-scene for
    experimentation, with the understanding that rebuilds re-bake them).
- The per-cell `pointOnSurfaceInfo` rivets read the surface shape's
  `worldSpace` plug, which carries the skinned deformation, so every cell's
  position AND orientation follow the deformed surface with no additional
  machinery. All revision-1/2 per-cell ring machinery (ringOffset
  transforms, per-row blends, OPM conjugations, delta/bend/stream node
  networks) is deleted; the cell stack reverts to
  npo -> FK control -> bind joint, and the future wave layer's slot moves to
  between the npo and the FK control.

### Resulting behavior (the contract riggers rely on)

- Translating a ring displaces its band; the surface between the fixed waist
  region and the moved band slants, so cells reorient from the slant -
  including row 0, whose position stays near the waist but whose orientation
  tilts. Influence falls off smoothly above and below per the weights.
- Rotating a ring about the axis twists the surface (tangentU rotates), so
  cells reorient in twist; tilting a ring tilts its band.
- Scaling a ring XZ bulges the band radially (flare stays band-local via the
  hat weights); Y scale stretches the band axially.
- Untouched rings leave the surface exactly undeformed (joints at rest),
  preserving neutrality under waistRef/root motion and uniform rig scale.
- The collider still resolves collision upstream; ring deformation composes
  downstream of it on the same surface, and can override collision on
  purpose.

### Public contract

- Rings live in the separate `ring_ctls` collection; the default ui host and
  the `root` relatives stay the first cell FK control. `relatives` /
  `controlRelatives` / `aliasRelatives` gain `ringKnee` always and
  `ringAnkle` only when present.
- `VERSION`: revision 3 shipped as `[1, 3, 0]`; the surface-follow anchors
  bump to `[1, 3, 1]` in both `__init__.py` and `guide.py`.
- The `ringScaleX/Y/Z` guide parameters and their preview ellipses
  (ADR-0001) are unrelated to this ADR: they size the collider node's leg
  collision rings, not these shaping controllers.

## Considered Options

1. Per-cell matrix deltas layered after the surface rivets (revisions 1-2)
   - Pros: no deformer, exact algebra.
   - Cons: cannot produce surface-consistent orientation response; rejected
     twice in Maya testing.
2. Driving the collider node inputs from the rings
   - Pros: no extra deformer.
   - Cons: the node's inputs are leg/bell matrices and scalar shape
     parameters; they cannot express local band sway or twist.
3. skinCluster on the rebuilt surface with station influence joints (chosen)
   - Pros: positions and orientations respond coherently and predictably
     (standard skinning intuition); deletes all bespoke matrix machinery;
     weights are the single tuning surface.
   - Cons: adds a deformer to the rig; ring scale flows through classic LBS
     (non-uniform joint scale on a NURBS surface), which is the intended
     flare but couples into the skin math rather than an explicit formula.
     The earlier objection that a deformer would invalidate UV calibration
     was wrong: calibration runs at rest, before any ring animation.

## Consequences

The behavior model becomes plain skinning, which matches animator intuition
and is tunable by weight profile alone. All bespoke delta machinery and its
review surface disappear (net code deletion). The ankle ring is independent
of the knee ring. Build cost: one skinCluster, up to three hidden joints and
two anchors. Cells and joints inherit deformation through the existing rivet
chain. Maya runtime validation (skinCluster on a NURBS surface, weight
baking via skinPercent, rivet response) is required; static checks cannot
cover it.

## Confidence and Revisit Trigger

Confidence: Medium (model is standard; the feel of the linear weight ramps is
unproven)

Revisit this ADR when:

- feel-testing wants different falloff (smoothstep, per-ring falloff
  parameters) or more stations.
- the wave ADR lands (its natural home may also be a surface-level effect
  rather than a per-cell offset).
- skinning artifacts appear on the NURBS surface (weight resolution is
  bounded by the rebuilt surface's CV count; the rebuild spans may need to
  increase).

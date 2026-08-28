# ADR-0002: Ring Shaping Controllers at Knee and Ankle Stations

Status: Proposed
Date: 2026-08-28
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

Design review: adversarial reviews by Codex and GLM, adjudicated through a Grok
counter-review that also verified the orchestrator's resolutions
(2026-08-28, artifacts under `docs/reference/skirt_design_review/adr2_*`).
The matrix algebra below was independently re-derived by two reviewers in
Maya's row-vector convention.

## Context

ADR-0001 builds `ymt_skirt_01` cells as collider-driven npos with a per-cell FK
control layer. Riggers need mid-level shaping across whole skirt bands: sway,
twist around the cone axis, and flare, without keying dozens of per-cell FK
controls. The rigger confirmed the interaction model: ring-shaped controllers
at the knee and ankle stations whose plain translate/rotate/scale channels
produce those effects implicitly; no explicit `twist`/`flare` float attributes.

A wave feature (sine plus noise) is explicitly deferred to its own ADR; this
ADR only reserves its slot in the per-cell transform stack.

Terms from ADR-0001 used here: cone axis `a`, waist origin, axial projection
`A` (distance along `a` from the waist), first-row centroid projection `A_0`,
hem projection `A_hem`, chain distances `d_hip`/`d_knee`/`d_heel`, per-row
fitted radii `(A_r, R_r)`, the bell frame (X = projected front, Y = `a`), the
per-cell driver world matrix `W_npo(t)`, and the internal reference
`waistRef`. Maya is 2022+ so `blendMatrix` and `offsetParentMatrix` are
available. Row-vector convention throughout: `multMatrix` computes
`matrixSum = in0 * in1 * ...`; a child's world matrix is
`local * offsetParentMatrix * parentWorld`.

## Decision

### Controllers

- Two circle controllers, `ringKnee_ctl` and `ringAnkle_ctl`, placed on the
  cone axis at stations `s_knee = min(d_knee, A_hem)` and
  `s_ankle = min(d_heel, A_hem)`.
- Short-skirt degeneracy: if `s_ankle - s_knee < 0.05 * A_hem` after clamping,
  the ankle ring is not built and the knee ring becomes the single, hem-ward
  ring.
- Controller frame: the bell frame translated to the station (X = projected
  front, Y = the cone axis toward the hem, Z completes right-handed). Circle
  radius = the cone radius at the station times 1.1, where the cone radius is
  linear interpolation over the fitted `(A_r, R_r)` samples with endpoint
  clamping: stations below `A_0` use `R_0`, stations at `A_hem` use `R_hem`
  (a convex combination of validated positive radii, so always positive).
- Color: the component IK color. All nine TRS channels keyable. No twist or
  flare attributes.
- Parenting: each ring control gets an npo under a visible
  `getName("ringCtls")` group at the component root; the npo is
  parent-constrained (maintain offset) to `waistRef`. The control's local
  matrix, including pivots and shear, must be identity at the end of
  `addObjects`; after one evaluation of the constraint the build asserts this
  within tolerance and raises otherwise. The control's own
  `offsetParentMatrix` stays identity.

### Per-cell application

- The per-cell transform stack becomes:
  npo (collider-driven, ADR-0001) -> `ringOffset` transform -> FK control ->
  bind joint. The FK control is re-parented under `ringOffset`; the deferred
  wave layer will insert between `ringOffset` and the FK control.
- Ring deltas isolate the animator's LOCAL edit, conjugated at the ring's
  current frame (no rest-matrix capture exists anywhere in this design):
  - Per ring i, with `P_i(t)` the ring npo world matrix and `L_i(t)` the ring
    control's local matrix (`ctl.matrix`):
    `delta_i(t) = inverse(P_i(t)) * L_i(t) * P_i(t)`
    via `multMatrix` [`P.worldInverseMatrix`, `ctl.matrix`, `P.worldMatrix`],
    one per ring, shared by all cells. An untouched ring (`L = identity`)
    yields `delta = identity` under arbitrary waistRef motion, root motion,
    and the supported uniform rig scale; a posed band under a shared rigid
    follow moves as a rigid body (verified in adjudication).
  - Per cell: `delta_cell(t)` = `blendMatrix` from identity with targets in
    the fixed order [`delta_knee`, `delta_ankle`] and node weights derived
    from the band coefficients (`w_knee`, `w_ankle`) baked at build time:
    `node_w_ankle = w_ankle`
    `node_w_knee = 0 if w_ankle == 1 else w_knee / (1 - w_ankle)`
    Because `blendMatrix` blends targets sequentially against the accumulated
    matrix, this mapping - not the raw band weights - realizes the effective
    coefficients (`w_knee`, `w_ankle`, identity `1 - w_knee - w_ankle`). With
    the weight functions below the node weights reduce to: rising span
    `(node_w_knee = w_knee, node_w_ankle = 0)` = slerp(identity, knee);
    falling span `(1, w_ankle)` = slerp(knee, ankle); hem `(0, 1)` = ankle.
    A three-way rotation mix never occurs. `blendMatrix` runtime behavior
    must be verified in Maya once at implementation time.
  - The `ringOffset` keeps identity local channels and identity pivots with
    `inheritsTransform` on; it is driven through its `offsetParentMatrix`:
    `OPM = multMatrix` [npo `worldMatrix`, `delta_cell`, npo
    `worldInverseMatrix`], giving the exact full-affine equality
    `W_ringOffset = W_npo(t) * delta_cell(t)` including shear (no
    `decomposeMatrix`, nothing dropped). Cycle rule: only the parent npo's
    `worldMatrix`/`worldInverseMatrix` plugs may feed this network; feeding
    `ringOffset.parentInverseMatrix` back into its own `offsetParentMatrix`
    is prohibited (it cycles).
- Consequence of this math, matching the agreed interaction model: translating
  a ring sways its band; rotating it about its Y swings cells around the cone
  axis through the station (twist); scaling XZ moves cells radially about the
  station (flare); tilting tilts the band; scaling Y stretches the band
  axially. Cells follow rigidly in proportion to their weight.

### Weights (baked per cell, row-uniform)

Every cell of row r is evaluated at the row centroid projection `A = A_r`
(the same statistic ADR-0001 uses for V mapping); axially scattered locators
within a row share the row's weights.

- `rise(A) = 1` if `s_knee <= A_0`, else
  `clamp((A - A_0) / (s_knee - A_0), 0, 1)`.
- Two-ring build:
  `w_ankle(A)` = 0 for `A <= s_knee`; `(A - s_knee) / (s_ankle - s_knee)` on
  `(s_knee, s_ankle)`; 1 for `A >= s_ankle`.
  `w_knee(A) = rise(A) * (1 - w_ankle(A))`.
  On the falling span `w_knee + w_ankle = 1`.
- Single-ring build: `w_knee(A) = rise(A)`, no ankle target.
- Continuity holds at `A_0`, `s_knee`, and `s_ankle` in all variants. Row 0
  is rigid exactly when `s_knee > A_0`; when the skirt is authored entirely
  below the knee (`s_knee <= A_0`) top-row rigidity is intentionally waived
  and the whole top band follows the knee ring. Falloff is linear in this
  version. The two-ring denominator `s_ankle - s_knee` is protected by the 5%
  degeneracy collapse.

### Scale and joints

- The full affine result (including any conjugation shear) flows through the
  FK control into the existing three-element
  `[fk_ctl, "{row}_{col}", "parent_relative_jnt"]` `jnt_pos` entries.
- The primary shaping result is positional: radial joint translation from
  conjugating ring XZ scale about the station. It is independent of joint
  scale policy.
- Non-uniform joint scale is secondary and configuration-dependent: mGear's
  `force_uniScale` rig option (stock default true) overrides the per-entry
  default, so this component does not pass a UniScale flag and does not fight
  the rig option; whether bind joints receive the non-uniform scale depends on
  that option. Segment scale compensation follows mGear's `force_SSC` /
  `addJoint` defaults. Revisit trigger below covers pipelines that need a
  hard guarantee either way.

### Public contract

- Rings live in a separate `ring_ctls` collection and are never appended to
  the cell `fk_ctls`; the default ui host and `relatives["root"]` /
  `controlRelatives["root"]` / `aliasRelatives["root"] = "skirtRoot"` remain
  the first cell FK control, unchanged from ADR-0001.
- `relatives` / `controlRelatives` / `aliasRelatives` gain `ringKnee` always,
  and `ringAnkle` only when the ankle ring exists (key absent otherwise,
  never aliased to the knee ring).
- Node names: `getName("ringKnee_npo"/"ringKnee_ctl"/"ringKnee_delta_mm")`
  and ankle equivalents; per-cell nodes
  `getName("skirt_{row}_{col}_ringBlend_bm")` and
  `getName("skirt_{row}_{col}_ringOpm_mm")`; the offset transform
  `getName("skirt_{row}_{col}_ringOffset")`.
- `VERSION` bumps to `[1, 1, 0]` in both `__init__.py` and `guide.py`.

## Considered Options

1. Explicit `twist`/`flare` float attributes driving per-cell math
   - Pros: discoverable channels.
   - Cons: duplicates what TRS conjugation provides; rejected by the rigger.
2. Rest-capture world delta `inverse(R0) * R(t)`
   - Pros: no follow-frame plumbing.
   - Cons: treats waistRef/root follow motion as ring input (double
     transform), violates the uniform-scale invariant, and makes rest capture
     build-order-sensitive. Rejected by review; replaced with the live
     local-edit conjugation.
3. Raw hat weights assigned directly as `blendMatrix` target weights
   - Pros: obvious.
   - Cons: `blendMatrix` accumulates sequentially, attenuating the cross-fade
     (0.75 at mid-span for equal deltas) and making target order silently
     load-bearing. Rejected; the node-weight mapping above is part of the
     contract.
4. Driving `ringOffset` TRS from a `decomposeMatrix`
   - Pros: mirrors the existing npo driver chain.
   - Cons: conjugating anisotropic bell-frame XZ scale into the tilted cell
     frame produces shear that TRS channels cannot hold; the claimed world
     equality would silently fail. Rejected in favor of `offsetParentMatrix`
     with the exact affine matrix.
5. Constraint-per-cell (point/orient/scale constraints to ring controls)
   - Pros: no matrix nodes.
   - Cons: three constraints per cell, no pivot-relative composition, worse
     performance. Rejected.
6. Deformer-based band shaping on the driving surface
   - Pros: single deformer.
   - Cons: deforms the surface the collider fitted, changing UV sampling and
     mixing shaping into the collision layer. Rejected.
7. Static ring parents under the component root
   - Pros: simplest parenting.
   - Cons: rings would not follow the waist once the interim references are
     constrained to the rig. Rejected (waistRef follow chosen).

## Consequences

Animators shape whole bands with two controls while keeping per-cell FK for
detailing, and joints inherit everything through the existing chain. The ring
layer composes after the collider, so it can violate collision on purpose.
An untouched ring is exactly neutral under any follow motion and uniform rig
scale; a posed band follows shared rigid motion as a rigid body. Build cost
per cell is one `blendMatrix` plus one `multMatrix` (cells whose weights are
exactly (0,0), (1,0), or (0,1) may skip the blend), plus one shared delta
`multMatrix` per ring. Anisotropic ring XZ scale produces genuine shear in
tilted cell frames; it is preserved end-to-end rather than dropped. Whether
bind joints receive non-uniform scale depends on the rig's `force_uniScale`
option; the positional flare does not. Short skirts may build with a single
ring; the 5% threshold is part of the contract. The stack order
npo -> ringOffset -> (future wave) -> FK is now fixed for follow-up ADRs.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- band shaping needs more than two stations (generalize the delta/weight
  machinery to N stations).
- linear band weights prove too harsh in motion (switch to smoothstep and pin
  it).
- the wave ADR lands and needs a different slot than between `ringOffset` and
  the FK control.
- the 5% single-ring threshold misclassifies real short-skirt assets.
- production requires a hard joint-scale guarantee (always or never): add an
  explicit `jnt_pos` UniScale element documenting the `force_uniScale` clash,
  or strip scale/shear with a `pickMatrix` on the joint driver.
- runtime verification of `blendMatrix` semantics in Maya contradicts the
  sequential model assumed here.

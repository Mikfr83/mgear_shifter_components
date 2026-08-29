# ADR-0005: Ring Generalization and Rig Ergonomics Batch

Status: Accepted
Date: 2026-08-29 (revision 2)
Owner: ymtshiftercomponents maintainers
Supersedes: these ADR-0002 items — the fixed knee/ankle ring pair and its
`ringKnee`/`ringAnkle` names and relatives, the uncalibrated 8-sample U
origin of the anchor level frame, the translate/rotate-only anchor drive,
and the 3-influence `_ring_skin_weights` formula. ADR-0002's conjugation
model, bindPreMatrix contract, and "rings deform the surface" architecture
remain in force.
Superseded by: none

Revision history:

- Revision 1: initial batch contract. 3-way review 2026-08-29: Codex high =
  Reject (2 BLOCKER), GLM = Approve-with-changes (2 MAJOR), Grok
  adjudication = Approve-with-changes (artifacts
  `docs/reference/skirt_design_review/adr5_review_codex.md`,
  `adr5_review_glm.md`, `adr5_adjudication_grok.md`).
- Revision 2 (this text): folds adjudicated M1–M7 and S1–S3/S5. Two
  adjudication notes: (a) GLM MAJOR 1 ("ring drag strength weakens by 1/s
  in stretched poses") was REFUTED by independent derivation — do not
  reintroduce it; (b) the adjudicator recommended keeping anisotropic
  anchor scale, but the rigger overrode this on 2026-08-29: the goal of
  anchor scale is ANIMATOR PICKABILITY (the circle must not end up buried
  inside the expanded surface), not exact surface tracing, so Decision 4
  now specifies isotropic max-ratio scale, which also closes the shear
  finding for every rotation axis instead of accepting a mild artifact.

## Context

`ymt_skirt_01` (component VERSION [1, 6, 0]) builds ring shaping controllers
at exactly two stations (knee and ankle, with a 5% single-ring collapse rule),
orients their anchors from raw surface U samples whose knot origin does not
align with the bell front, transfers only translate/rotate to the anchors,
exposes only collision/tightness/falloff of the `skirtBellCollider` solver,
creates the seven leg reference transforms flat under one group, and parents
every cell npo flat under the component root.

The rigger requested six improvements (2026-08-29 interview, decisions
recorded inline):

1. Arbitrary ring controller count → decision: explicit `ringPositions`
   list parameter, "auto" keeps the physically meaningful knee/ankle pair.
2. Expose the solver's new `smoothness` / `follow` dials (fork ADR-0001,
   colliders repo) as host channels.
3. Ring anchor orientation is unintuitive → decision: calibrate X to the
   bell front only; Y stays hem-ward (explicitly NOT flipped).
4. Ring anchors should auto-scale with the surface so the control circle
   stays pickable; exact tracing is NOT required (rigger decision,
   2026-08-29).
5. Hierarchize waistRef → hipRef → kneeRef → heelRef.
6. Group the row/col npos.

Backward compatibility is explicitly waived by the rigger for this batch:
existing guides and downstream steps may require re-authoring. Component and
guide VERSION become [2, 0, 0].

Terms from ADR-0001/0002: cone axis `a`, waist origin, axial projection `A`,
hem projection `A_hem`, rebuilt surface (pre-ring-skin) with U = circumference
and V = waist→hem, relative ring skinning via live
`bindPreMatrix = anchor.worldInverseMatrix`.

## Decision 1: `ringPositions` string parameter (arbitrary ring count)

New guide parameter `ringPositions` (string, default `"auto"`).

Grammar (pinned; hard build failures in the style of existing validators):

- Strip the WHOLE string first. `"auto"` (exact, case-sensitive after the
  strip): legacy stations. `s_knee = min(d_knee, A_hem)`, `s_ankle =
  min(d_heel, A_hem)`, collapsing to the single ankle station when
  `s_ankle - s_knee < 0.05 * A_hem` (current `_ring_stations` unchanged,
  expressed as a station list of length 1 or 2).
- Otherwise: split on ASCII comma, strip each token. An EMPTY token is an
  error (this rejects leading/trailing/double commas). Parse each token
  with Python's invariant-locale `float()` (which itself tolerates
  surrounding whitespace — implementers must not add a divergent strip);
  `nan`/`inf` are rejected by the finiteness check. Locale decimal commas
  are therefore invalid by construction (`"0,3"` splits into two tokens and
  fails range checks).
- Each value must be finite, `0 < t_i <= 1`; the sequence strictly
  increasing; adjacent separation `t_{i+1} - t_i >= 1e-3` and
  `t_1 >= 1e-3` (normalized hem fractions, dimensionless at any guide
  size). `N >= 1`; a sanity cap `N <= 32` guards against pasted garbage
  (the real usable bound is surface resolution, below). No auto-collapse:
  an explicit list is authoritative and too-close entries are an error,
  not a merge.
- Every parse/range error message echoes the full raw `ringPositions`
  string, the 1-based token index, and the raw offending token (style of
  `_validated_grid_matrices` missing/extra/duplicate reporting).

Bounds reality (adjudicated wording): the grammar itself bounds N at about
1000 (separation floor), the sanity cap at 32, and the USABLE count is
bounded by the rebuilt surface's V resolution — a clamped cubic with
`rebuildSpansV` spans has `spansV + 3` V CV rows (7 at the default 4), and
a ring whose hat support contains no CV row is dead (guard below).

Naming becomes uniformly indexed regardless of mode: controllers
`ring<i>_ctl`, anchors `ring<i>_anchor`, joints `ring<i>_jnt`, relatives and
aliases `ring0 .. ring{N-1}` (hem-most ring has the highest index).
`ringKnee` / `ringAnkle` names and relatives are removed (compat waived).

Ring skin weights generalize to a piecewise-linear hat basis over the station
list `T = (0 = s_0(waist), s_1, ..., s_N)`; for a CV with axial projection
`A`:

- `A <= 0`: waist weight 1.
- `s_i <= A <= s_{i+1}`: `w_{i+1} = (A - s_i) / (s_{i+1} - s_i)`,
  `w_i = 1 - w_{i+1}`, all other weights 0.
- `A >= s_N`: `w_N = 1`.

This is a partition of unity by construction and reduces EXACTLY to the
current `_ring_skin_weights` for N = 2 and N = 1 (verified algebraically by
both reviewers; the current knee factor `clamp(A / s_knee) * (1 - ankle_w)`
equals the hat form on each segment). The skinCluster gains one influence
per ring; the existing waist influence and live bindPreMatrix wiring are
unchanged in structure, only looped over N + 1 influences.

Dead-ring guard (adjudicated): a CV only ever feeds the two influences
bracketing it, so a station whose open support `(s_{i-1}, s_{i+1})` misses
every CV row receives zero weight everywhere while the partition-of-unity
assert still passes. After baking, the build MUST require, for every ring
influence `i = 1..N`, max CV weight `> 1e-6` (weights are non-negative, so
this is a liveness check at the numerical floor; no separate "softness"
threshold). Failure names the ring index, its `ringPositions` token, the
current `rebuildSpansV`, and the remedy: "raise rebuildSpansV or widen/move
stations so a CV row falls inside (t_{i-1}, t_{i+1})". At default
`rebuildSpansV = 4` the rest V CV rows cluster near Greville abscissae
{0, 1/12, 1/4, 1/2, 3/4, 11/12, 1}, whose interior gaps are 0.25 of hem —
even a 3-station list can dead-ring (e.g. `0.3, 0.375, 0.5`).

Ring control circle radius stays `_station_radius(s_i) * 1.1`.

## Decision 2: host channels for solver `smoothness` / `follow`

New guide parameters `smoothness` (double, default 0.0, range 0..1) and
`follow` (double, default 0.0, range 0..1), new settings-UI double spin
boxes, new anim params `smoothness` / `follow` connected to the
`skirtBellCollider` node attributes of the same names, and initial
`setAttr` in `_configure_collider` (same pattern as collision/tightness/
falloff).

Plugin gate: `_ensure_colliders_plugin` currently verifies node registration
only. After the collider node is created, the component MUST verify
`cmds.attributeQuery` for both `smoothness` and `follow` on the instance and
raise a RuntimeError naming the Maya version and the remedy ("rebuild the
colliders plugin") when either is missing. Rationale: a silent skip would
build a host channel wired to nothing or silently drop a requested feature;
strict failure matches the existing postCollision/wave gates, and
compatibility with stale plugin builds is explicitly out of scope.

Defaults 0/0 keep the solver on its bit-identical legacy path (fork
ADR-0001 D6 stage 1), so a freshly built rig behaves exactly as before until
the dials are raised.

## Decision 3: anchor X calibrated to the bell front

`_connect_anchor_surface_follow` currently samples 8 U values starting at
the knot origin (`u = minU + k/8 * span`). The knot origin's angle around
the cone axis is arbitrary (the same fact that forces the per-column
calibration in `_surface_u_parameters`), so the anchor X axis
(`X = normalize(sample[0] - sample[4])`) lands at an arbitrary spin.

Fix (per-target-angle selection, adjudicated S1): per ring, at the ring's
`v_i`, scan K = 256 U values on the rebuilt surface at
`u = minU + (index / K) * span` for `index = 0..K-1` (the K-th value would
duplicate the periodic seam and is excluded), computing each sample's
cone-axis angle with `_surface_angle` (angle 0 = bell front). Then select
EACH of the eight sample parameters independently: for target angles
`theta_k = k * pi / 4`, `u_k = argmin |wrap(angle - theta_k)|`, tie-broken
by the lowest scan index. The build asserts the eight selected U values are
distinct, then proceeds unchanged: `d1 = sample[0] - sample[4]` (front
diameter), `d2 = sample[2] - sample[6]` (side diameter), frame construction
as today (Y from the cross of the diameters with the rest-time order flip
so rest Y points hem-ward, X from d1, Z = X x Y), with the existing
degenerate d1/d2/cross thresholds.

Why per-angle instead of `u_front + k/8 * span`: uniform U offsets only
give the cardinal angles when angle is linear in U. That holds for the
collider's native circumference parameterization (its CVs sit at uniform
parametric angle and the ring collision is radial, i.e. angle-preserving),
but `rebuildSpansU > 0` re-parameterizes U toward arc length on the
DEFORMED shape, where equal U is no longer equal angle — and raising
rebuildSpansU (16–24) is a recommended setting since the round-3 smoothing
work. Per-angle selection costs zero extra samples (same 256-scan) and is
robust to both paths and to a reversed U winding.

Properties:

- Rest X now points to the projected bell front at every ring; rotate
  handles match the character's front/side intuition.
- The calibration is rest-time only; live orientation still comes from the
  connected posi samples, so surface twist/tilt follow is unchanged.
- Y intentionally stays hem-ward (rigger decision): it matches the bell
  frame (bell Y = waist→heel axis) and flipping it would invert the feel of
  every ring's rotate channels.
- The scan is per ring (at `v_i`), not reused from the column scan at mid-V:
  cost is negligible at build time and it stays correct even if the fitted
  cone tilts the iso-U lines across V.

## Decision 4: isotropic anchor auto-scale (pickability)

Purpose (rigger decision 2026-08-29): keep the ring control circle
PICKABLE when the surface expands — the circle must not end up buried
inside the deformed surface. Exact tracing of the surface ellipse is a non-
goal; that decision overrides the adjudication's keep-anisotropic
recommendation and closes the reviewed shear finding entirely.

Effective skin algebra (adjudicated derivation, Maya row vectors,
`p' = sum_i w_i * p * bindPreMatrix[i] * jointWorld[i]`, `world = local *
parentWorld`): with anchor world `A`, control local edit `C`, joint at
identity under the control, and live `bindPreMatrix = A^-1`, the
per-influence matrix is the conjugation

```
M = A^-1 * C * A
```

NOT a complete cancellation (GLM's review claim to the contrary was refuted
in adjudication — a translation edit moves the band exactly as far as the
gizmo, `t * A_linear` for both; there is no 1/s drag weakening). The
consequence of conjugation is that edits are expressed in the anchor's
basis. If `A`'s linear part were anisotropically scaled, conjugated
rotations would pick up non-orthogonality (shear); with an ISOTROPIC scale
`A` is a similarity transform, conjugation maps every rotation to a
rotation, and no shear can appear for any edit on any axis.

Mechanism, per ring:

- Transform the four cardinal sample positions (indices 0, 4, 2, 6) into
  the anchor's PARENT space (`vectorProduct` operation 4, point-matrix
  multiply, against `anchor.parentInverseMatrix[0]` — the shared `ringCtls`
  group), then measure `lenFront = distance(local s0, local s4)` and
  `lenSide = distance(local s2, local s6)` with distanceBetween nodes.
  Parent-space measurement is what prevents component-root scale `q` from
  double-applying (world-space lengths carry `q`, the anchor inherits `q`
  again, and the world scale would be `q^2` against a surface scaled `q` —
  reviewed BLOCKER, confirmed).
- Rest lengths `r1, r2` are read once at build IN THE SAME parent space;
  each must be `>= 1e-5 * guide_size`, else RuntimeError (degenerate ring
  diameter).
- `ratioX = lenFront / r1`, `ratioZ = lenSide / r2` (one multiplyDivide,
  operation 2), then `s = max(ratioX, ratioZ)` via a condition node
  (greaterThan). `max`, not the mean: under anisotropic deformation the
  mean leaves the circle buried along the major axis, while `max` keeps it
  at or outside the surface on both axes (the existing 1.1 radius margin is
  retained on top).
- Connect `s` to `anchor.scaleX`, `anchor.scaleY`, AND `anchor.scaleZ`.
  All three axes matter: an XZ-only "uniform" scale (sy = 1) is still
  anisotropic as a 3D map and would shear conjugated X/Z tilts; the full
  isotropic scale commutes with every rotation. scaleY has no visual side
  effect (the circle lies in the XZ plane) and cancels out of the skin like
  every other anchor channel when the control is at identity.

Safety and asserts: at rest both ratios are exactly 1, so
`_assert_ring_control_identity` (which reads only the control, never the
anchor) passes unchanged. The scale network reads the pre-ring-skin
`rebuildSurface.outputSurface` samples the frame already uses, so no DG
cycle. The frame axes pass through `normalizeOutput = true` vectorProduct
nodes, so `decomposeMatrix.outputScale` of the level frame is always 1 and
cannot be used instead; the separate length measurement is required, and
the anchor's shear channels stay untouched at 0.

## Decision 5: leg reference hierarchy

`_create_internal_references` builds, per side:

```
colliderRefs
  waistRef
    hipRef_L
      kneeRef_L
        heelRef_L
    hipRef_R
      kneeRef_R
        heelRef_R
```

Placement still uses `cmds.xform(worldSpace=True)` with the same aim/bell
matrices, so world rest poses are identical to the flat layout, and every
consumer (`skirtBellCollider`, `skirtCollideDeformer`, ring waist anchor
constraint) reads `worldMatrix[0]` and is unaffected by parenting.
`FIXED_REFERENCE_NAMES` is already ordered parent-before-child per side, so
creation order needs no change; only the `parent=` argument becomes the
previous ref in the chain (waist for both hips).

New default semantics (pinned per review): an UNCONSTRAINED child ref now
inherits its parent ref's world motion. A connect step that used to
constrain waist + knees and leave the heels static previously fed static
heel matrices to the collider; after this change the heels ride their knee
parents. This is the intended ergonomic (constraining waistRef alone
carries the whole chain; per-limb constraints layered on children resolve
in parent space and simply override), and it is the criterion the one-time
connect-step review must check against. Channel state (unlocked,
non-keyable, hidden from channel box) is unchanged.

## Decision 6: npo grouping

New static groups under the component root:

```
root
  skirtCtls_grp
    skirtRow0_grp
      skirt_0_0_npo ...
    skirtRow1_grp
      ...
```

Groups are identity transforms created before the cell loop; each npo is
created with `parent=` its row group. The npo drive chain already multiplies
by the npo's own `parentInverseMatrix[0]`, so a static intermediate parent is
mathematically transparent; `cmds.xform(worldSpace=True)` placement is
likewise unaffected. Row groups give per-row visibility toggles for free
(translating a row group is compensated and does nothing — visibility is
the only effective control, which is the intent). Ring anchors keep their
existing `ringCtls` group.

## Data contracts (delta summary)

- Guide params added: `ringPositions` (string, "auto"), `smoothness`
  (double 0..1, 0.0), `follow` (double 0..1, 0.0). All are REQUIRED by the
  component (strict validators, no `.get` fallback) — old guides must be
  re-saved (compat waived).
- guide.py integration points (pinned per review): `Guide.addParameters`
  registers all three params; `componentSettings.populate_componentControls`
  initializes the widgets (`setText` for the ringPositions line edit,
  `setValue` for the two spin boxes); `componentSettings.
  create_componentConnections` persists them (`editingFinished` →
  update for ringPositions, `valueChanged`/`updateSpinBox` for smoothness
  and follow). Widgets live in settingsUI.py (`ringPositions` QLineEdit,
  `smoothness`/`follow` QDoubleSpinBox 0..1 step 0.05). The string-param +
  lineEdit pattern has in-repo prior art (`ymt_feather_ribbon_01` rowNames).
- Component/guide VERSION: [2, 0, 0] in both `__init__.py` and `guide.py`.
- Relatives/controlRelatives/aliasRelatives: `root`, `ring0..ring{N-1}`,
  grid cell entries unchanged. `ringKnee` / `ringAnkle` removed.
- Node-name additions per ring i: `ring<i>_anchor`, `ring<i>_ctl`,
  `ring<i>_jnt`, `ring<i>_center_avg`, `ring<i>_center<k>_posi`,
  `ring<i>_d1_pma` / `_d2_pma`, `ring<i>_*Axis_vp`, `ring<i>_level_fbfm`,
  `ring<i>_center_mm` / `_dm`, `ring<i>_s<k>Local_pmm` (k = 0, 2, 4, 6),
  `ring<i>_lenFront_db` / `_lenSide_db`, `ring<i>_ratio_md`,
  `ring<i>_scaleMax_cnd`.
- `_ring_skin_weights(A, stations)` replaces the 3-influence signature; it
  returns N + 1 weights (waist first). Build asserts: each CV's weights sum
  to 1 within 1e-6 AND each ring influence's max CV weight exceeds 1e-6
  (dead-ring guard, Decision 1) before `skinPercent`.

## Verification plan (user-side Maya, plus build-time asserts)

1. Default guide (`ringPositions = "auto"`): build succeeds, two rings,
   every ring ctl X axis points to the character front (visual), local
   identity assert passes, skin behavior matches the previous release when
   dials stay 0 (rings untouched → surface identical).
2. `ringPositions = "0.3, 0.6, 0.9"`: three rings at those hem fractions,
   hat weights partition (build assert), each ring shapes only its band.
   Negative case: `"0.3, 0.375, 0.5"` at default `rebuildSpansV = 4` must
   fail closed with the dead-ring message naming the middle ring.
3. Leg-spread pose: anchors scale uniformly so ctl circles stay at or
   outside the surface (pickable); with all ctls at identity the surface is
   bit-identical to a build without Decision 4 (bindPreMatrix
   cancellation). Drag a ring ctl in the spread pose: band and gizmo world
   displacements match ~1:1 (the refuted 1/s weakening must NOT appear).
4. Component root scaled 0.5 and 2.0 (uniform), identity and posed rings:
   circles track the surface scale `q`, not `q^2`.
5. `smoothness` / `follow` host channels exist, connect, and drive the
   solver; building against a stale plugin fails with the rebuild message.
6. Moving waistRef moves the whole reference chain; collider inputs
   (worldMatrix) at rest are identical to the flat layout.
7. Outliner shows `skirtCtls_grp/skirtRow<r>_grp` with all npos inside; row
   visibility toggles work; cell behavior unchanged.
8. `rebuildSpansU = 16`: ring X still lands on the bell front (per-angle
   selection path).

## Alternatives considered

- `ringCount` + even spacing: rejected — loses the knee/ankle physical
  placement and cannot express uneven layouts.
- Ramp attribute for ring positions: rejected — guide-param string is
  simpler to author/serialize than a ramp on the guide root.
- Per-ring guide locators: rejected for now — heavier authoring; the
  normalized list covers the need; revisit only if per-ring orientation
  authoring is ever required.
- Flipping anchor Y to point up: rejected by the rigger (keeps bell-frame
  consistency and current rotate feel).
- Soft-skip when the solver lacks `smoothness`/`follow`: rejected — silent
  feature loss; strict failure is consistent with the other plugin gates and
  compat with stale builds is explicitly out of scope.
- Deriving anchor scale from decomposeMatrix: impossible — the frame axes
  are normalized upstream, so the frame matrix carries no scale.
- Anisotropic anchor scaleX/Z (adjudication-preferred): rejected by the
  rigger — the goal is pickability, not exact tracing, and isotropic scale
  keeps every rotation edit shear-free instead of accepting a mild
  non-orthogonality on X/Z tilts.
- Display-only shape-scale split (scale a shape-holder under the ctl, keep
  the skin path unscaled): rejected — severs the surface-sized manipulation
  basis and is unnecessary once the scale is isotropic.
- Mean of the two diameter ratios: rejected — buries the circle along the
  major axis under strong ellipticity; `max` guarantees non-buried on both
  axes.
- Ring-count integer cap as the dead-ring defense: rejected as a substitute
  — the per-influence coverage assert is the invariant; the N <= 32 cap is
  only typo defense.

## Consequences

- Breaking release [2, 0, 0]: renamed ring relatives, three new required
  guide params. Existing guides need a settings-UI touch/re-save; downstream
  custom steps referencing `ringKnee`/`ringAnkle` must switch to `ring<i>`,
  and connect steps must account for the new child-ref inheritance default
  (Decision 5).
- `python/ymt_components/ymt_skirt_01/README.md` must be updated: ADR-0005
  in the ADR index, the `ringPositions` authoring grammar, the
  `smoothness`/`follow` host channels, the renamed ring relatives, and one
  line that usable ring count is limited by `rebuildSpansV` (7 V CV rows at
  the default 4 cubic spans) with the build failing closed on a dead ring.
- Build cost: one 256-sample U scan per ring (rest-time only) plus 4
  pointMatrixMult, 2 distanceBetween, 1 multiplyDivide, and 1 condition per
  ring at runtime — negligible.
- The solver dial plumbing depends on the rebuilt colliders plugin (fork
  ADR-0001); Maya versions whose mll predates it fail the build loudly.

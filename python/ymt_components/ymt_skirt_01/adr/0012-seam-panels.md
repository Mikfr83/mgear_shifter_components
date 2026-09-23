# ADR-0012: Seam panels for collider surfaces and cell wiring

Status: accepted (2026-09-22; records the wiring contract in plans/cut-panels-wiring.md).
Maya 2026 acceptance: tests/ymt_skirt_01/test_cut_panels.py, 15 tests passed and 1 skipped
(plugin-side case) on 2026-09-22 with yddColliders 5.0.0 and mGear develop.

Partially supersedes ADR-0001: the single outputSurface consumer, whole-surface
U calibration, centroid-only hem extent, and unconditionally closed guide rows.
Partially supersedes ADR-0005: single-surface ring sampling and skinning,
centroid-based ring station extent, and the single-surface dead-ring check.
Partially supersedes ADR-0008: N6's unconditional closed row curve and name;
fragment names follow G1 below. Global cell naming, hierarchy and joint order remain.
Partially supersedes ADR-0010: the major-4 plugin requirement and singular
surface/deformer graph become the panel graph below. Evaluation space E and
its supported root transforms remain unchanged.
Partially supersedes ADR-0011: P1/N1's shared uvPin and global pin index,
O3/R1/S1's unconditional periodic neighbours, O5's localized string readback,
D5's exclusion of material calibration checks, and X2's unchanged ring/deformer
wiring. Position offset algebra, chain aim, global joint indices, E boundaries,
and component/guide VERSION [0, 1, 0] remain in force.
The wave normalization statements in ADR-0004 and ADR-0006 are also replaced
by D3 below; phase remains geometric and driven by current input values.

## Context

A slit must separate collider output, surface fitting, sampling and cell
adjacency below its start row. Cutting only the generated surface leaves
neighbour-based aims reading the other bank and does not define how multiple
surfaces receive ring shaping, waves or final collision correction.
Asymmetric hem locators also require individual material-height samples;
a row centroid alone cannot describe the hem.

The detailed numerical contract is
[cut-panels-wiring.md](../plans/cut-panels-wiring.md), Reviewed v3, with the
[recorded decisions](../plans/cut-panels-wiring-decisions.md). Its chapters
1–2 define guide inputs, material calibration, protected rows, hem sampling
and failure handling; chapters 3–7 define the panel graph and guide display;
chapters 8–9 separate plugin acceptance from component acceptance.

## Decision

Row increases from waist to hem; gap g lies between col g and col (g+1) mod
cols. Coordinates and row-vector matrices follow ADR-0010/0011.

### Guide inputs and display (G)

- G1. `seams` is a required string, default empty, containing comma-separated
  integer `g:r` tokens. r is the first cut row. Require in-range indices,
  unique nonadjacent gaps including wrap adjacency, and at most 32 tokens.
  Preserve token order: token i writes seams[i] and identifies panel i+1.
  Guide parsing and build parsing share the same validator and diagnostic
  format. Rows with no active gap retain `skirtRow<r>Crv`; active rows draw
  open `skirtRow<r>_<k>Crv` fragments starting just after the smallest active gap.
- G2. `followRange` is required, finite and nonnegative, default 0.1875,
  passed directly to the collider. It is separate from host follow strength.
- G3. Row 0 starts at height zero. For r>0, write
  h=max(t[r-1], 1e-6), require t[r]>h+1e-9 and h<1-1e-9.
  The floor preserves a shared seated waist row. Plugin rows at t=h remain
  shared; inserted start-height rows must survive surface fitting.

### Material panels and validation (P)

- P1. Require the yddColliders panel, follow-range, reference-height
  and protected-V attributes. Always consume outputPatches, including the
  reserved uncut panel 0 over [0,1]. No outputSurface consumer or old-guide,
  old-rig or old-plugin compatibility path remains.
- P2. Calibrate column mean angles and circular gap mean angles against the
  uncut patch at V=0.5. Sample max(256, cols*64) material positions, then
  bisect the nearest short wrapped interval 40 times when bracketed.
  Reject undefined gap angles, seam parameters within periodic distance
  1e-9 of each other, and seams within 1e-6 of a column.
- P3. Force evaluation through surface MPlugs while capturing collider-prefixed
  MGlobal error messages. Require exactly the expected patch ids, identical
  vBreaks across panels, and each internal start height within 1e-9 of a break.
  A clustered break below h gets one retry at break+1.5e-9. Require
  rebuildSpansV >= len(vBreaks)+1 without automatic resolution increases.
- P4. Assign each column once to its open material interval, unwrap and sort
  within that interval, and retain its panel-local rank k_col. Seamless panel
  0 may contain a column on the periodic origin. Column and joint naming
  remain global and col-major.
- P5. Retain per-column hem projections, including the top-row seating shift.
  The maximum projection determines fitted extent and ring station extent;
  row centroids still determine row V. Normalize each hem projection by
  surface_length, cap at 1, require positive projection and H>beta+1e-9,
  where beta=max(vBreaks), or zero when empty. Samples increase in local U.
  Cut endpoints copy the nearest column height. Uncut endpoints share the
  linear interpolation across the last/first-column wrap. Coalesce columns
  within 1e-12 of an endpoint. Omit panelHems only when all H are exactly 1;
  otherwise write all panels and require exact hemHeightSamples readback.
- P6. Validate guide inputs before creating component content. Record the
  scene node set after input validation and remove every subsequently created
  node on material calibration, seam or hem failure, including temporary
  shapes, samplers, reference matrices and collider transforms. Errors after
  panel validation retain mGear's existing partial-build behavior. This
  component boundary does not itself roll back mGear's earlier hierarchy.

### Surfaces and cells (C)

- C1. Each panel gets colliderSurface_p<id>, its shape and its own fit.
  Connect outputPatches[id].surface to inputSurface and vBreaks to
  protectedVParameters. Surfaces are identity in E and inherit root placement.
- C2. Create one skirtCells_p<id>_uvPin per panel on the final shape.local.
  Calibrate column U only on the assigned panel and retain shared row V.
  Pin indices are k_col*rows+row; joint indices remain col*rows+row. The
  default host remains skirt_0_0_ctl, independent of panel ordering.
- C3. Remove next across an active gap col and previous across an active gap
  col-1. Use the remaining one-sided difference at a bank; above the start
  row retain both neighbours, even across panels. Rest frame, winding,
  geometry validation and live aim use the same neighbours. Signed tangent
  subtraction still has two inputs; a missing neighbour uses the cell itself.
  ADR-0011's P=offset*F position layer and longitudinal aim are unchanged.
- C4. Resolve aim enum labels as before, set their values, then compare integer
  getAttr readback. Localized asString results are not validation inputs.

### Rings and deformers (D)

- D1. At each ring station, scan 256 U samples on every fit. Choose a panel/U
  pair for each of eight target directions by minimum wrapped angular error.
  POSI nodes read these pre-skin fit outputs; the anchor frame and isotropic
  maximum-diameter scale formulas remain unchanged.
- D2. Each panel receives its own ringSkin -> optional wave -> optional
  postCollide chain, verified in that order. Skin influences, live bind-pre,
  E geomMatrix and caching remain unchanged. Bake weights from each panel's
  CV projections; test ring liveness using the maximum over all panels.
- D3. Every wave uses heightNormalization=1 and a live connection from
  collider.outputReferenceHeight to referenceHeight. Set collider
  referenceMaterialHeight=surface_length and bellScale1=1.0, so all panels
  share material-height normalization, including on asymmetric hems.
- D4. Every post-collision deformer reads its own hidden intermediate rest
  duplicate. Host wave channels and postFalloff connect to every corresponding
  panel deformer. Shared leg reference inputs remain in E.

## Considered options

- Retaining a periodic surface for seamless skirts: rejected because it leaves
  two graph paths and prevents common material calibration and validation.
- One deformer with multiple geometry inputs: fewer nodes, but geometry shares
  one evaluation task. Separate deformers permit independent panel evaluation
  and local surface rebuilding; node counts grow with panel count.
- Sorting seam tokens by angle: rejected because token order defines plugin
  logical indices and panel identity.
- Separate ring anchors and controls for each bank: would remove shared ring
  influence, but changes the animator interface and shaping behavior. Retain
  shared rings with the approximation stated below.
- Automatically increasing fit resolution or substituting guide defaults:
  rejected because either hides an invalid authored build input.

## Consequences

Seams remove direct cell adjacency below their first cut row while retaining
the shared upper skirt. Controls and bind joints keep their names, count and
global order. New computational surface, pin and deformer names always include
the panel id, including p0. Existing rigs require rebuilding and custom steps
that address the former single surface must use the panel collections.

Ring anchors average samples across both banks. Contact on one bank can move
a shared ring anchor and affect the other bank through ring edits and skinning.
This approximation is accepted for this wiring; complete bank independence is
not promised. The isolation test disables ring skin and post-collision envelopes,
follow and smoothness to measure the direct collider/cell path.

Nonuniform hems retain one V per row. Surface positions on short columns need
not match intermediate locators; rest offsets restore cell positions before
subsequent deformation. More panels add fits, skins, pins, deformers and build
sampling. Node count alone does not establish playback performance.

## Revisit triggers

- Shared ring movement across a slit prevents required animator control.
- Production layouts require adjacent gaps, a column on a seam, or a hem above
  a protected row.
- Panel count makes build sampling or deformation dominate measured latency.
- Geometric wave phase needs stable material coordinates beyond shared height.
- Whole-Shifter-build atomic rollback becomes required in addition to P6.

## Maya acceptance tests

`tests/ymt_skirt_01/test_cut_panels.py` implements contract chapter 9 T1–T15;
T16 remains in the plugin suite. Run through Maya 2026 mayapy with mGear solvers
and yddColliders loaded. Inspect actual graph connections, rest matrices,
inserted knots, exact bank isolation, hem readback and failure node sets.
The full-build no-node expectation also exposes nodes created by mGear before
P6's snapshot. The reversed-fixture test retains the specified negative winding
expectation rather than changing its sign to match the implementation.
Static checks cannot establish these runtime outcomes.

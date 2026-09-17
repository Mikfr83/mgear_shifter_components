# ADR-0009: Leg profile stations in the guide, preview, rig plumbing, and mesh fitting

Status: accepted (drafted 2026-09-14; contract review by sonnet and Grok, implementation review by sonnet and Muse; verification recorded in the colliders repository under docs/validation/leg-profile.md).
Depends on the plugin contract colliders `docs/adr/0005-leg-profile-stations.md`
(node attributes `thighRadiusX/Z`, `kneeRadiusX/Z`, `calfRadiusX/Z`,
`ankleRadiusX/Z`, `thighPosition`, `calfPosition`; all multipliers of
`ringScale`, defaults 1.0 and 0.5). 
(additive; existing guides build unchanged because every new parameter
defaults to the value that reproduces the current output).

## Context

The guide exposes one leg thickness (`ringScaleX`, `ringScaleZ` times half
the hip separation) and the rig sends it to both collider nodes as
`ringScale`. The plugin now accepts four stations (thigh, knee, calf,
ankle) as multipliers of that hip ellipse, forming a convex envelope along
the leg. Entering ten numbers by hand is acceptable as a fallback, but the
usual source of truth is the character's body mesh, so the settings UI
gets a fitting action that measures the stations from a mesh.

## Decision

Terms: "station" and "leg parameter s" as in the plugin ADR. "Side" is L or
R. The guide reference positions are `hip_<side>`, `knee_<side>`,
`heel_<side>`.

### Guide parameters (P)

- P1. Add double parameters with the same names as the node attributes:
  `thighRadiusX`, `thighRadiusZ`, `kneeRadiusX`, `kneeRadiusZ`,
  `calfRadiusX`, `calfRadiusZ`, `ankleRadiusX`, `ankleRadiusZ` (default 1.0,
  minimum 0.001), `thighPosition` and `calfPosition` (default 0.5, range
  0.0 to 1.0).
- P2. Add a string parameter `profileMesh` (default empty): the short or
  full name of a mesh shape, or of a transform whose hierarchy contains the
  body's mesh shapes (bodies split into parts are named by their group). It
  is a guide-time input only; the rig build never reads it.
- P3. `ringScaleX`, `ringScaleZ`, `ringScaleY` keep their meaning. The hip
  ellipse remains `hip separation * 0.5 * ringScaleX/Z`.

### Settings UI (U)

- U1. A new group "Leg profile" under the ring scale rows holds one row per
  station with two spin boxes (X, Z) using the existing ring scale spin box
  factory, and two rows for `thighPosition` and `calfPosition` (0.0 to 1.0,
  step 0.05). Editing any of them updates the parameter and redraws the
  ring preview (same pattern as `_update_ring_scale`).
- U2. The group also holds a line edit bound to `profileMesh`, a button
  "Use selection" that writes the first selected mesh transform's name into
  it, and a button "Fit profile from mesh" that runs F1..F7 and then writes
  the fitted values into the spin boxes and the preview.
- U3. Preview: `update_ring_preview` draws, per side, ellipses at hip,
  thigh, knee, calf, and heel. Thigh sits at `hip + (knee - hip) *
  thighPosition`, calf at `knee + (heel - knee) * calfPosition`. Radii are
  the hip radii times the station multipliers; hip and heel use the hip
  ellipse and the ankle multipliers respectively. The ellipse plane normal
  follows the current code: Hip and Thigh use the hip-to-knee axis; Knee,
  Calf, and Heel use the knee-to-heel axis. Preview names keep the
  `_ringPreview<Label>_<side>_Crv` pattern with labels Hip, Thigh, Knee,
  Calf, Heel.
- U4. The falloff sentence of ADR-0003 ("RELATIVE to the local ring
  radius") is amended: the band is relative to the per-axis local radius
  (`ringScale` times the station multiplier along the profile). With all
  multipliers at 1.0 this is the current behaviour.

### Rig plumbing (R)

- R1. `_configure_collider` and `_create_post_collision_deformer` set the
  ten node attributes from the ten guide parameters with `cmds.setAttr`.
  No multiply nodes: the values are multipliers and therefore invariant
  under the root scale compensation that `ringScale` needs.
- R2. Validation at build: every radius multiplier must be finite and
  greater than 0; both positions must be finite and within [0, 1].
  Otherwise raise RuntimeError naming the parameter and value. Do not
  substitute defaults.
- R3. The rig does not require `profileMesh` to exist.

### Fitting action (F)

The action measures the convex envelope of the mesh around each leg and
writes the guide parameters. It runs in the guide scene, in world space,
on the mesh as posed at that moment (bind pose expected).

- F0. Typing: the fitting code talks to `maya.api.OpenMaya` (MFnMesh,
  MFloatPoint, MFloatVector, MMeshIsectAccelParams). Before F1..F7, add the
  structural protocols the code needs to `ymt_shifter_utility/type_protocols.py`
  (for example a mesh function set protocol with `closestIntersection` and
  `autoUniformGridParams`) or narrow with `typing.cast` at the API boundary.
  Never annotate with `Any` or `object`.
- F1. Input resolution: `profileMesh` must name an existing mesh shape, or
  a transform with at least one non-intermediate mesh shape anywhere below
  it; otherwise stop with an error naming the value. Every resolved shape
  is sampled: a ray's hit is the nearest hit over all shapes. Use
  `maya.api.OpenMaya.MFnMesh` with world-space points. Build one MFnMesh
  and one acceleration structure (`autoUniformGridParams`) per shape per
  fitting run and reuse them for every ray. Target: a 50k-triangle body
  fits in under 2 seconds.
- F2. Frames: for each side build the two segment frames from the guide
  positions with the same construction the preview uses (segment axis
  normal, root-front projected as the X axis, cross product as Z). Segment
  A is hip to knee, segment B is knee to heel.
- F3. Sections: sample each segment at 17 parameters `t = i / 16`,
  i = 0..16. The section center is `start + (end - start) * t`. At each
  section cast 32 rays from the center in the section plane, at angles
  `2 pi k / 32` measured from the frame X axis (k = 0 is +X), with
  unit-length directions, using `MFnMesh.closestIntersection` and
  `maxParam` = 4 times the hip separation (the bound only guards against
  runaway rays; the other leg is rejected by the test below, not by the
  ray length). A ray that hits nothing is skipped. Keep a hit only if its
  distance to this side's segment (as a finite segment, not a line) is
  strictly smaller than its distance to the other side's corresponding
  segment (A against A, B against B); equal distances are discarded.
- F4. Section extents: `rX` is the largest absolute X coordinate of the
  kept hits in the frame, `rZ` the largest absolute Z coordinate. A
  section with fewer than 8 kept hits is invalid.
- F5. Stations: hip = section A t=0; knee = the per-axis maximum of
  section A t=1 and section B t=0 (the two frames differ when the knee is
  bent, and the knee value feeds rings of both orientations); heel =
  section B t=1; thigh = the section of A
  with the largest `rX + rZ` among t in (0, 1), and `thighPosition` = its
  t; calf = the same over B and `calfPosition`. If hip, knee, or heel is
  invalid, stop with an error naming the station and side. If no interior
  section of a segment is valid, the station falls back to the linear
  interpolation of its neighbours at position 0.5 and a warning names the
  segment. When several interior sections tie for the maximum (relative
  difference below 1e-6, as on a cylinder), the station radii are the tied
  value and the station position is the arithmetic mean of the tied
  sections' t values, so a fully flat segment reports position 0.5.
- F6. Envelope: no convexity is enforced. Thigh and calf are interior
  maxima by construction, so they never fall below the sections they were
  chosen from; a knee larger than the thigh maximum is legitimate and is
  kept as measured. The only correction is clamping values below 0.001 to
  0.001, applied to the absolute radii before any ratio is formed.
  Concavities between stations disappear because the profile is linear
  between stations.
- F7. Write-back: average the two sides per station and axis, excluding
  a side whose station came from the F5 fallback; if both sides fell back,
  use the fallback value. The same exclusion applies to the positions. Set
  `ringScaleX = hipX / (hip separation * 0.5)` and likewise Z, then the
  station multipliers `stationX / hipX`, `stationZ / hipZ`, and the two
  positions. Refresh the spin boxes and the preview. Report the absolute
  radii per side and station, and which stations used the fallback, with
  `pm.displayInfo` so the user can judge the fit.

### Tests (T)

- T1. Extend the colliders integration check (orchestrator-owned): build
  with `kneeRadiusX = 0.7` and confirm both nodes carry the ten values;
  build with defaults and confirm both nodes hold 1.0 / 0.5.
- T2. Fitting on a synthetic mesh with a unique peak per segment: per leg,
  a lofted surface (or a polyCylinder whose section rings are scaled per
  height) with radius 1.0 at the hip, 1.2 at 40 percent of the thigh, 0.9
  at the knee, 1.1 at 50 percent of the calf, 0.6 at the ankle, placed on
  the guide positions; the fitted multipliers must match the known ratios
  within 5 percent and the positions within 0.1. Run headless with the
  settings methods on a stand-in object, as the rebuild check does.
- T4. The colliders integration check expects component and guide VERSION
  [4, 1, 0] after this change (orchestrator-owned edit).
- T3. Fitting failure: an empty `profileMesh` and a non-mesh name each stop
  with the documented error and leave the parameters unchanged.

## Consequences

- Manual entry remains possible; fitting is a convenience that writes the
  same parameters.
- Both legs share one profile on the node; asymmetric legs are averaged.
  Per-side profiles would need per-side node attributes and are out of
  scope.
- The mesh is sampled by ray casting in the section plane, so clothing or
  accessories on the mesh inflate the envelope; the user selects the body
  mesh, not the clothed one.

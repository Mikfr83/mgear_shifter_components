# ADR-0008: Column-major grid naming and vertical grid hierarchy

Status: accepted (2026-09-14). Supersedes the grid naming and the flat
grid layout of ADR-0001, and the per-row control groups and flat joint
list of ADR-0005.

## Context

Grid locators, controls, and joints are named "skirt_<row>_<col>". Users
read the first number as the position around the skirt and the second as
the depth toward the hem, so the current order is reversed from intuition.
The guide grid is flat under the guide root, so moving a locator does not
carry the locators below it, and the rig joints are all siblings under the
parent-relative joint, so a skinned mesh cannot use the natural
waist-to-hem chain that other FK chains provide.

## Decision

Terms used below: "col" is the index around the circumference (0 .. cols-1),
"row" is the index from the top row toward the hem (0 .. rows-1). The guide
parameters keep their names "rows" and "cols" and their meaning.

### Naming (N)

- N1. The grid locator local name is "skirt_<col>_<row>_loc". The regular
  expression stays "^skirt_(\d+)_(\d+)_loc$"; group 1 is col, group 2 is row.
- N2. Every rig node built per cell uses the stem "skirt_<col>_<row>":
  the pointOnSurfaceInfo "_posi", fourByFourMatrix "_fbfm", "_npo",
  multMatrix "_mm", decomposeMatrix "_dm", and the control "_ctl".
- N3. The joint name passed to jnt_pos is "<col>_<row>" (mGear applies the
  joint naming rule and the jnt extension).
- N4. relatives, controlRelatives, and aliasRelatives use the locator local
  name "skirt_<col>_<row>_loc" as key and "<col>_<row>" as alias.
- N5. Error messages that name a cell use the col_row order.
- N6. Row display curves keep the name "skirtRow<row>Crv" and connect the
  cols of one row in col order, closed.
- N7. Internally the rig may keep cell tuples in any order, but every string
  that reaches the scene or a message is produced by one helper per module
  so the order is written in one place.

### Guide hierarchy (G)

- G1. In the guide, "skirt_<col>_0_loc" is a child of the guide root and
  "skirt_<col>_<row>_loc" for row >= 1 is a child of
  "skirt_<col>_<row-1>_loc".
- G2. Locators keep their world positions; parenting is world-preserving.
  Serialized transforms (guide.tra) stay world matrices as today.
- G3. Creation order when drawing from a template and when rebuilding from
  the settings UI is col-major (col outer, row inner), so a parent always
  exists before its child.
- G4. The settings UI rebuild parents the new locators the same way. Deleting
  the previous grid must not raise when a child was already removed with its
  parent.
- G5. Collection from a scene guide (setFromHierarchy) records the parent
  local name of every grid locator in addition to the world matrix. The parent
  of a locator directly under the guide root is recorded as "root".
- G6. The rig build validates, after the existing missing/extra/duplicate
  check, that every recorded parent matches G1. On the first mismatch it
  raises RuntimeError naming the locator, the expected parent, and the actual
  parent. A flat guide from an older version therefore stops with a message
  that names "skirt_0_1_loc" (or the first offending locator) and its parent.
  When no parents were recorded (build from a guide that was never in a
  scene), the check is skipped.

### Control groups (C)

- C1. The static group "skirtCtls_grp" under the component root contains one
  group per col named "skirtCol<col>_grp" (replacing the per-row groups of
  ADR-0005). Each col group holds the npos of that col in row order.
- C2. Col groups are identity transforms created before the cells; the npo
  drive chain already multiplies by the npo's parentInverseMatrix, so the
  grouping is transparent to the rest pose and to the surface following.
  A col group therefore gives a per-col visibility toggle, mirroring the
  guide and joint chains; it does not propagate control animation down the
  col (the controls of a col remain independent).

### Joint hierarchy (J)

- J1. When addJoints is on, joints are registered col-major: for each col,
  row 0 first, then rows 1 .. rows-1.
- J2. The row 0 entry uses the parent-relative joint as its parent (the
  existing "parent_relative_jnt" option). Each entry for row >= 1 uses the
  joint created immediately before it, i.e. the cell (col, row-1). With
  mGear's jnt_pos list form this is a two-element entry [ctl, name]; mGear
  then keeps the last created joint as the active parent.
- J3. jointRelatives maps "skirt_<col>_<row>_loc" to the index of that joint
  in jointList, and "root" to the index of joint (0, 0). Indices follow the
  registration order in J1, so index = col * rows + row.
- J4. Ring influence joints (ADR-0002) are not part of jnt_pos and are
  unchanged.
- J5. The joint transform is still driven from the control world matrix
  through the mGear joint connection, so the hierarchy changes only the
  parent relationship and the skin's inverse-scale chain, not the rest pose.

### Versioning and documentation (V)

- V1. VERSION in __init__.py and guide.py becomes [4, 0, 0].
- V2. README.md documents the col_row naming, the guide parent chain, the
  joint chain, and that guides from versions before 4.0.0 fail closed and
  must be rebuilt with the settings UI "rebuild grid" button.

## Consequences

- Old guides and old rigs are incompatible. This is accepted by the user.
- The integration check in the colliders repository
  (tests/integration/check_wave_component.py) must populate the guide with
  the new names and expect version 4.0.0. It is updated by the orchestrator.
- The plugin helper script in the colliders repository (yddColliders.py
  "skirt_<i>_<j>_posi") is a separate tool and is out of scope.

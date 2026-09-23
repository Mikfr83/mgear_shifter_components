# ADR-0013: Column root FK controllers feed the collider as pre-solve offsets

Status: accepted (2026-09-23). Plugin-side decision: colliders ADR-0010
(docs/adr/0010-column-fk-offset.md); plugin contract docs/plans/column-fk-offset.md
(yddColliders 5.1.0). Component wiring: [column FK wiring contract](../plans/column-fk-wiring.md).

Extends ADR-0012 (seam panels) and ADR-0008 (column groups). Cell controls,
pins, deformer order and the evaluation space E are unchanged.

## Context

With seam panels a raised leg facing a seam has no geometric rule for which
side each bank escapes to: the seam CV sits on the leg axis and the
collider's radial relax flips sides within one degree of sweep. The user
decided not to automate that choice in the solver. The animator chooses by
moving the columns next to the seam before the collider solves.

## Decision

- C1. Each column gets one FK controller `skirtCol<col>_fk_ctl` at the
  column root (waist row position), parented under a group on the `root`
  side that does not depend on the collider output. It must not live under
  the pin-driven cell npos (cycle).
- C2. The controller's delta from rest (worldMatrix times the inverse of its
  rest worldMatrix, expressed in the column root rest frame: tangent, radial,
  axis) is connected to the collider's per-column offset sample together with
  the column's calibrated material U (`_calibrate_material_u`).
- C3. Translation and rotation are both animatable. No per-column collider
  weight; the collider applies lift, relax and follow after the offset.
- C4. Rig-side automation (driving the same sample from leg angles) is
  allowed and stays outside the plugin.

## Consequences

- Requires yddColliders 5.1.0 (column offset input). Rest pose output is
  bit-identical to 5.0.0 when all deltas are identity.
- Tests: rest identity, seam-adjacent column moved sideways removes the
  seam-crossing pop measured on the plugin side, waist row receives the
  offset too.

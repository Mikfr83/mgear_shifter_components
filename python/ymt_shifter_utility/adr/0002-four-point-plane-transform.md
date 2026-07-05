# ADR-0002: Four-Point Plane Transform Utility

Status: Proposed
Date: 2026-06-08
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

## Context

Rig components and custom tools sometimes need a transform that follows the orientation of a deforming quadrilateral without depending on a mesh rivet or surface UV. The important contract is the plane orientation from four ordered points; the centroid is only the transform position.

The utility must stay compatible with Maya embedded Python 3.9 and should be built from Maya dependency nodes so the result updates when the source transforms move.

## Decision

Shared utility code will provide a four-point plane transform helper. The helper creates a new transform and connects Maya nodes that:

- place the transform at the centroid of four ordered point transforms,
- derive a plane basis from the quadrilateral horizontal and vertical directions,
- orient the plane normal toward a reference local axis on a normal transform,
- map the plane normal onto a caller-selected local axis.

The helper will validate the initial inputs and fail clearly when required transforms are missing or the four points cannot form a stable plane.

## Considered Options

1. Build this per component
   - Pros: Each caller can tailor axis behavior locally.
   - Cons: Duplicates fragile matrix and vector node wiring.
2. Use a temporary mesh or uvPin rivet
   - Pros: Maya already solves surface orientation.
   - Cons: Requires generated geometry or UV assumptions for a four-point transform-only problem.
3. Use a shared Maya-node utility
   - Pros: Centralizes the contract and remains live in the DG.
   - Cons: Adds a public utility API that must preserve axis semantics.

## Consequences

Callers get a reusable transform constraint without adding mesh assets. The helper is limited to ordered quadrilateral inputs and does not provide maintain offset or existing-target connection behavior in its first version.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- callers need maintain-offset behavior,
- callers need to drive an existing transform instead of creating one,
- runtime fallback is required for source points that become degenerate after creation.

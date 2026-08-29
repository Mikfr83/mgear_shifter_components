# ADR-0003: Ordered Loop Symmetrization Utility

Status: Proposed
Date: 2026-08-20
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

## Context

Guide layouts such as lip outlines contain transform nodes ordered around a
closed shape. These layouts need bilateral position symmetry, but their seam
representation depends on node-count parity: odd-length lists duplicate the
seam at the first and last nodes, while even-length lists contain the seam node
only once.

## Decision

Shared utility code will symmetrize an ordered list of transform positions
across a caller-selected plane. The utility will:

- use the plane normal and a point on the plane as explicit inputs,
- average each position with the reflected position of its partner so neither
  side is treated as the authoritative source,
- project self-symmetric seam and opposite nodes onto the plane,
- place both seam nodes at one position for odd-length lists,
- preserve node rotations and scales.

The utility accepts explicit node names and also supports Maya's ordered
selection for interactive use.

## Considered Options

1. Copy one side onto the other
   - Pros: Preserves the authored source side exactly.
   - Cons: Requires an additional side-selection contract and discards edits on
     the destination side.
2. Average reflected pairs
   - Pros: Produces symmetry with the smallest balanced positional adjustment.
   - Cons: Neither original side remains unchanged.
3. Implement parity handling in each component
   - Pros: Each component can define its own seam convention.
   - Cons: Duplicates selection-order and reflection logic across guide tools.

## Consequences

Callers must supply nodes in closed-outline order. Odd-length lists explicitly
represent the seam twice; even-length lists represent it once. The first API
version changes only world positions and does not mirror rotations, scales, or
shape data.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- guide tools need one-way source-to-destination mirroring,
- orientation symmetry becomes part of the shared contract,
- components require automatic loop-order discovery.

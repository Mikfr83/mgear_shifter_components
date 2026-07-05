# ADR-0006: Consume Parent Fold For Parametric Fan Close And Ordinal Tilt

Status: Proposed
Date: 2026-07-05
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: ADR-0007 (fold offset driver mechanism only)

## Context

`ymt_birdwing_3jnt_01` gains a master `fold` anim attribute with guide-authored arm fold pose and automatic FK pull (parent ADR-0003 "Add Master Fold Attribute With Automatic FK Pull"). The arm fold already reaches this component through the existing `get_feather_ribbon_refs()` connections: anchors, curl translations, the ribbon surface, rivets, and detail chains all follow the folded arm with no changes here.

What the arm fold cannot produce is the feather-specific part of a folded wing: the fan closing (feather chains converging toward a common trailing direction) and ordered stacking (feathers layering like a closing hand of cards instead of interpenetrating at random).

Design review rejected storing a second folded pose for every detail point (guide bloat, duplicate maintenance) and decided the feather-side fold is generated from a small set of parameters. Design review also required that every control stay live at any fold value, consistent with ADR-0003 "Separate Detail Rivets From Length-Preserving Chains": fold must be an additive offset layer, not a pose override.

## Decision

- `connect_ymt_birdwing_3jnt_01` reads `refs["metadata"].get("fold_attr")`. When the entry is absent (older parent build, or parent guide without fold locators), the component builds exactly as before.
- Two per-row guide settings are added, parsed and normalized against `rowNames` like the existing per-row settings:
  - `foldFanClose`: fan-close gain per row, 0.0-1.0, default 1.0.
  - `foldTiltSteps`: stacking tilt in degrees per feather order step, default 0.0 (feature off).
- Fan close is computed at build time from rest geometry, with no new guide locators: for each feather (row, section), the signed yaw about the wing normal from that feather root's chain direction to the row's convergence direction, where the convergence direction is the rest chain direction of the row's last section. Feathers already aligned with the trailing feather rotate little; leading feathers rotate most. At runtime the applied yaw is `yaw_i * foldFanClose_row * fold`.
- Ordinal tilt orders the stack: `tilt_i = foldTiltSteps_row * section_index * fold`, applied about the feather chain long axis.
- Both rotations are applied on a new `{detail}_fold_npo` transform inserted between `chain_npo` and `aim_npo` of each feather chain root (col 0 only), rotate order XYZ with tilt on X and yaw on Y. The drivers are two multiply nodes per feather root fed by the parent fold plug.
- The fold layer is purely additive above the rivet/aim extraction layers. The ribbon surface and rivet references are not modified by fan close, so there is no feedback loop between fold and aim extraction.

## Considered Options

1. Guide second pose for every detail point
   - Pros: fully WYSIWYG folded feather layout.
   - Cons: doubles detail guide count; high maintenance; rejected in design review in favor of parameters.
2. Animate rivet UV parameters so feather roots slide together
   - Pros: feathers physically converge on the surface.
   - Cons: fights the uvPin/rivet machinery, changes aim extraction inputs, and risks feedback between fold and the surface-derived orientation layer.
3. Additive fold offsets on dedicated npo transforms driven by build-time computed angles (chosen)
   - Pros: no guide bloat; no feedback; all controls stay live; trivial runtime cost.
   - Cons: feather roots rotate in place rather than sliding, so strong folds rely on the parent arm fold to bring roots together.

## Consequences

Within a row the ordinal tilt is monotonic in section order, so the stacking order is guaranteed; cross-row layering is tuned with per-row `foldTiltSteps` values. At `fold = 1` every anchor, curl, and detail control plus the `detailCurlRotMult` attributes remain functional, and intermediate fold values are produced by the live surface + aim machinery rather than pose interpolation.

The settings UI needs fields for the two new per-row settings with the same normalization flow as `detailCurlRotMults` (preserve existing values, append defaults for new rows, drop removed rows).

Maya runtime validation is required for the folded extreme: the folded surface brings adjacent rivets close together, and fan-close yaw compounds on top of the aim rotations extracted there. This extends the strong-curvature validation demand from ADR-0003. Fold pose authoring on the parent guide must keep adjacent rivets separated.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- converging on the row's last-feather direction is insufficient and an explicit per-row convergence target (`foldFanTargetU`) is needed.
- stacking needs depth-based lift in addition to ordinal tilt.
- folded feathers need root slide along the surface (rivet UV animation) rather than rotation in place.

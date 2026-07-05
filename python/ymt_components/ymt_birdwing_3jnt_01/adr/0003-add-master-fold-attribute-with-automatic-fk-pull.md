# ADR-0003: Add Master Fold Attribute With Automatic FK Pull

Status: Proposed
Date: 2026-07-05
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

## Context

Animators need an on-screen wing fold/unfold performance: a single `fold` value that transitions the wing between the spread build pose and a folded pose while the transition itself stays presentable. The folded pose is mostly an arm tri-fold (root/elbow/wrist/hand), which belongs to `ymt_birdwing_3jnt_01`, plus feather fan-close and stacking, which belong to the `ymt_feather_ribbon_01` child (ADR-0006 in that component).

The wing arm is animator-driven through an FK chain and an IK chain blended per bone by the `blend` anim attribute (`node.createPairBlend` on the `wingBones` result chain, plus wrist anchor constraint weights and FK/IK control visibility). A folded pose cannot be expressed through the IK chain because IK pins the wrist to the animator's `ik_ctl`. Any fold mechanism that fights the IK target produces unpredictable results.

Blending a stored final pose over the result chains was rejected during design review: the stored pose lives in a different space than the live surface-driven pose, linear pose blending passes through implausible intermediate shapes, and animator controls go dead at the folded extreme.

## Decision

Fold is applied at the input layer so every downstream mechanism stays live:

- Add a `fold` anim param (double, 0.0-1.0, default 0.0; 0 = spread build pose, 1 = folded) on the uiHost, proxied to the main controls like `blend`.
- The guide gains optional second-pose locators `foldElbow`, `foldWrist`, `foldHand`, and `foldEff`, chained like the main guide chain (`foldElbow` under `root`). When any fold locator is missing, the component builds exactly as before: no fold attribute, no fold offsets, and no fold entry in the feather ribbon contract metadata.
- At build time, per-FK-bone local rotation deltas from the build chain to the fold chain are computed as minimal-twist from-to rotations evaluated in each parent bone frame. A `fk{i}_fold_npo` transform is inserted between `fk{i}_npo` and `fk{i}_ctl`, driven by a `pairBlend` in quaternion interpolation mode from identity to the stored delta, weighted by `fold`. Animator FK edits stack on top of the fold offset.
- Automatic FK pull: `effectiveBlend = blend * (1 - clamp(fold / foldFkPullEnd, 0, 1))`. `foldFkPullEnd` is a guide setting (double, default 0.5), so the arm finishes pulling to FK before the feather fan finishes closing. All existing `blend` consumers are rerouted to `effectiveBlend`: the `wingBones` pairBlend weights, the wrist deform anchor constraint weights, and FK/IK control visibility. The `blend` anim attribute itself remains untouched raw animator input.
- `get_feather_ribbon_refs()` metadata gains a `fold_attr` entry carrying the fold anim param plug name when fold is enabled, so child feather ribbon components can consume the same master value.

## Considered Options

1. FK-only fold with no blend interaction
   - Pros: simplest implementation; no interaction with IK tooling.
   - Cons: fold does nothing while the wing is in IK; animators must remember to switch modes first.
2. Drive the IK target and up-vector npos from fold as well
   - Pros: fold works in both modes.
   - Cons: composes fold with the animator's `ik_ctl` pose, producing hard-to-predict results; contradicts the pinned-wrist nature of IK.
3. Automatic FK pull through an effective blend value
   - Pros: fold works from either mode with one attribute; behavior converges to the predictable FK path; raw `blend` stays animator-owned.
   - Cons: IK/FK match tooling that reads the raw attribute sees a value that no longer reflects the effective state while folded.
4. Procedural per-bone fold angles instead of guide pose locators
   - Pros: no guide changes.
   - Cons: folded silhouettes need WYSIWYG authoring; numeric trial and error was rejected during design review.
5. Aim-with-up-vector fold deltas instead of minimal-twist from-to rotations
   - Pros: explicit twist authoring.
   - Cons: the build-pose normal is unreliable as an up vector across a large fold arc and invites flips; twist styling can instead be layered by FK controls on top of the fold offset.

Option 3 with guide pose locators (option 4 rejected) and minimal-twist deltas (option 5 rejected) is chosen.

## Consequences

Fold interpolates along per-bone rotation arcs computed by the live FK machinery, so intermediate values are plausible and every control (FK, corrective, feather ribbon) stays functional at any fold value.

The IK/FK match and transfer tools (`rmbmenu.py` `space_switch_ikfk`, `control.ikFkMatch` on the uiHost `wing_blend` attribute) keep reading and writing the raw attribute. While `fold >= foldFkPullEnd` the effective blend is fully FK, so matching or switching has no visual effect until fold is lowered. This is accepted and must be documented for animators; match tooling is not modified by this ADR.

Old guides without fold locators rebuild identically. The feather ribbon contract change is additive and optional.

Maya runtime validation is required for: quaternion interpolation flips at extreme fold poses, skinning quality at the folded elbow/wrist angles, and the visual continuity of the FK pull overlapping soft IK and stretch fade-out.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- minimal-twist from-to deltas produce unwanted twist in production fold poses and authored up vectors or full fold-pose orientations become necessary.
- animators need fold to operate while staying in IK.
- IK/FK match tooling needs to become effective-blend aware.

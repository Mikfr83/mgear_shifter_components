# ymt_skirt_01

Collider-driven skirt component wrapping `yddSkirtBellCollider`. Contracts
live in `adr/` (0001 base, 0002 ring controllers, 0003 two-pass
collision, 0004 wave oscillator, 0005 ring generalization and rig
ergonomics, [0006 directional wave expression](adr/0006-directional-wave-expression.md),
[0007 ydd plugin identity](adr/0007-ydd-plugin-identity.md),
[0008 grid naming and hierarchy](adr/0008-grid-column-major-naming-and-hierarchy.md),
[0009 leg profile and fitting](adr/0009-leg-profile-guide-and-fitting.md),
[0010 component-local evaluation](adr/0010-component-local-evaluation.md),
[0011 chain-aim cell frames](adr/0011-chain-aim-cell-frames.md),
[0012 seam panels](adr/0012-seam-panels.md), and
[0013 column root FK offsets](adr/0013-column-root-fk-offset.md)).

Version 0.1.0 requires a yddColliders plugin with yddSkirtSurfaceFit,
yddSkirtBellCollider, yddSkirtCollideDeformer, and yddSkirtWaveDeformer.
The component loads `yddColliders` even when the upstream `colliders` plugin is loaded.
Guides require `seams` and `followRange`; missing parameters are rejected.
There is no migration path for guides without these parameters or for 4.x plugins.
Open old rigs with the archived old plugin, then rebuild from their guides
or migrate the required data. The new node names and IDs do not load old
rigs as the same node types.

## Grid naming and hierarchy

Grid names use col_row order: col runs around the circumference and row
runs from waist to hem. Locators are named `skirt_<col>_<row>_loc`;
controls and cell drivers share the stem `skirt_<col>_<row>`.
Each column's row 0 guide locator is under the guide root, and each later
row is under the previous row's locator, preserving world positions.
Controls are grouped by column: `skirtCtls_grp` holds one
`skirtCol<col>_grp` per column with that column's `_npo` nodes in row
order. The groups are static; controls in a column stay independent.
With addJoints enabled, joints are registered column by column with names
`<col>_<row>`: row 0 is under the parent-relative joint and each later row
is under the previous row's joint.

Rebuild Grid Locators places each row outside the leg profile. It computes a
required radius from half the hip separation plus the larger X/Z leg radius,
then applies a fixed clearance of 0.15 and a hem flare of 0.3. These are
placement constants and are not guide settings. The guide does not validate
the resulting placement during rig construction; placement remains the
rigger's responsibility.

Guides predating the column-major grid contract in ADR-0008 fail closed
and must be rebuilt using the settings UI rebuild grid button before
building the rig. For guides without leg profile parameters, opening the
component settings dialog adds them with their defaults (the Guide Manager
update does the same).

## Guide reference placement

The waist, hip, knee, and heel references define the collider cone; the
grid rows define the skirt. The build does not depend on where the rows sit
relative to those references. Rows above the waist reference seat the bell
origin on the top row. A hem above the hips or below the heels clamps the
node `height` to its [0.01, 1] range and maps rows past the surface end onto
the surface hem frame. These clamps emit a warning. Seam starts and individual hem heights must
also satisfy the constraints below. Rest offsets place controls at their guide
positions before downstream deformers; post-collision can subsequently move them.

## Ring controls and collider channels

`ringPositions` defaults to `auto`, which places the legacy knee/ankle
stations (two rings), collapsing to a single ring only when the two
stations sit within 5% of the hem projection of each other. To author stations
explicitly, enter a strictly increasing comma-separated list of normalized
hem fractions, for example `0.3, 0.6, 0.9`. Values must satisfy
`0 < t <= 1`, the first and adjacent separations must be at least `0.001`,
and no more than 32 entries are accepted.

Ring relatives are named `ring0` through `ring{N-1}`, ordered waist to hem.
The former `ringKnee` and `ringAnkle` relatives are not exposed.

The ui host exposes `smoothness` and `follow` channels in the 0..1 range;
their guide defaults are 0.1 and 0.2 respectively, and they drive the matching
`yddSkirtBellCollider` attributes.

Usable ring count is bounded by `rebuildSpansV`: the default four cubic
spans produce seven V CV rows, and the build fails closed if any ring has
no weighted CV row (raise the V spans or widen/move the stations).

## Slits and hem shape

`seams` is a string, empty by default. Enter comma-separated `g:r` integer
pairs: gap `g` lies between columns `g` and `(g + 1) mod cols`, and `r` is
the first cut row. With five rows and eight columns, `1:2,5:2` opens two
slits from row 2; `1:1,5:3` opens them at different rows; `1:0` cuts from
the waist. Whitespace is allowed, and whitespace alone means no seams.

Require `0 <= g < cols`, `0 <= r < rows`, at most 32 tokens, unique gaps,
and no adjacent gaps, including the last/first gap pair. Adjacent gaps
would leave a panel with one column. Empty tokens, nonintegers, duplicate
gaps, and out-of-range values fail with the raw string and token number.
Token order determines panel ids; tokens are not sorted by angle or gap.
A seam overlapping a column within material U distance 1e-6, coincident
seam parameters within 1e-9, or a gap with no defined mean angle is rejected.

For `r > 0`, the seam starts at `max(t[r-1], 1e-6)`, where `t` is row
centroid projection divided by the fitted surface length and clamped to
[0, 1]. The preceding row is shared and row `r` must exceed that start by
more than 1e-9. Starts at or beyond `1 - 1e-9` are rejected. The 1e-6 floor
keeps a seated waist row shared when `r=1`; `r=0` instead writes zero.
Drawn guide rows remain closed above the slit and become open fragments
at and below its first cut row.

`followRange` is a finite, nonnegative double, default 0.1875, passed
directly to the collider's followRange. For example, 0.25 sets that range
to 0.25 without changing the host's separate `follow` strength.

Individual hem locator projections generate each panel's hem samples.
The longest column sets the fitted hem extent and ring station scale;
row V still uses row centroids. Normalized hem heights are capped at 1
and must exceed the highest protected V row (`beta`) by more than 1e-9.
Cut panel endpoints take the nearest column's height; seamless endpoints
share the value interpolated across the periodic wrap. All-unit hems omit
`panelHems`; otherwise every panel receives a sample array.

## Surface fit and cell tracking

Each panel reads `yddSkirtBellCollider.outputPatches[id].surface` through its
own `yddSkirtSurfaceFit` into `colliderSurface_p<id>Shape`. The fit's
`protectedVParameters` stays connected to that patch's `vBreaks`.
No component consumer reads `outputSurface`, including on a seamless skirt:
that case uses the reserved panel 0 over material U [0, 1]. With seams,
panel ids are 1 through the number of seam tokens, in token order.

`rebuildSpansV` sets each fit's cubic V span count (1..256, default 4).
It must be at least `len(vBreaks) + 1`; insufficient resolution raises an
error with the required count instead of increasing it automatically.
The fit preserves the patch's open U structure and protects the inserted
seam-start V rows. It approximates the rest of the collider surface.

Ring anchors sample eight directions across all panel fit outputs before
skinning. Each panel has its own `skirtCells_p<id>_uvPin` sampling its final
shape's `local` geometry in component-local evaluation space E, with
normalizedIsoParms disabled, normalAxis=1, tangentAxis=0, and
relativeSpaceMode=1. A column belongs to exactly one panel; its U is
calibrated on that panel. Columns are sorted by unwrapped material U within
the panel, and the pin index is `k_col * rows + row`. This index is separate
from the unchanged global joint index `col * rows + row`.
Row V remains shared across columns, including for an asymmetric hem.

Each cell has a multMatrix that computes P = offset × F, where F is its
uvPin frame and offset = M0 × inverse(F0) is constant. A decomposeMatrix
extracts the position p. This preserves the locator rest position and the
contribution of uvPin rotation to position when the rest offset is nonzero.

A plusMinusAverage subtracts neighbouring column positions in the order
selected by the component winding sign. At an active seam it uses a
one-sided difference on that bank; above the start row it retains the
cross-seam neighbour. Rest and live frames use the same adjacency. An aimMatrix
points local Z at the next row position; the hem uses the previous span
in the same waist-to-hem direction. Local X follows the signed column
chord projected perpendicular to Z, and Y = cross(Z, X). The rest frame M0
uses these same chords from guide positions only. One winding sign is
chosen from cell (0, 0), the first cell in col-major scan order, and must
agree across all rest cells so rest Y points outward. Cell rest frames no longer use pointOnSurfaceInfo samplers.

The aimMatrix output drives npo.offsetParentMatrix with an identity local
matrix. The FK cube remains a child of that npo and starts with identity
local and offsetParentMatrix transforms. Joint registration is unchanged.

Construction validates rest chord lengths and projected tangent directions,
then winding, before creating position nodes. It validates sampled positions
before creating any aim nodes. It also checks uvPin frame finiteness and
orthonormality, offset values, integer aim enum readback and defaults, aim connections,
rest aim and world matrices, and control identity. These checks precede
ring skin, wave, and post-collision connections. A single warning lists
cells whose locator-to-uvPin rest distance exceeds 0.1 × guide_size in E;
those distances determine how strongly uvPin rotation affects position.
Runtime degeneracy has no fallback or previous-frame retention.

See [ADR-0011](adr/0011-chain-aim-cell-frames.md),
[ADR-0010](adr/0010-component-local-evaluation.md), and the
[local evaluation plan](plans/local-evaluation-and-performance.md).

## Panel deformers

Each panel has an independent chain:
`fit -> ringSkin_p<id>_skc -> wave_p<id>_def -> postCollide_p<id>_def`.
The guide toggles omit wave or post-collision when disabled. Ring skin
shares the ring influences and live bind-pre matrices, but weights are
baked from each panel's CV projections. The dead-ring check considers all
panels together. Each post-collision node reads its own hidden static
`postCollide_p<id>_rest` shape. Host wave channels and `postFalloff` drive
all corresponding panel deformers; the default host stays `skirt_0_0_ctl`.

Every wave uses `heightNormalization=1` (ReferenceHeight) and a live
`outputReferenceHeight -> referenceHeight` connection. The collider's
`referenceMaterialHeight` is the fitted surface length with `bellScale1=1`.
Shortening one bank therefore does not independently renormalize its wave.

Ring anchors still average eight samples across banks. Contact on one bank
can change the shared anchor and, with ring edits, affect other panels
through ring skin. Per-panel deformers remove direct surface and cell
adjacency across active seams; they do not provide complete independence
through shared ring controls.

## Column root FK

columnFk defaults to true. Each column has a skirtCol<col>_fk_ctl at its
waist root, with translation and rotation channels in tangent, radial, and
bell-axis directions. Use these controls to choose which side of a slit each
bank moves toward before the collider solves. The controls feed the collider
pre-solve column offsets using each column's calibrated material U.

Set columnFk to false to omit the rest-frame sampling, group, anchors,
controls, and collider column inputs. The bundled yddColliders plugin must
still provide columnOffsetMatrix and columnMaterialU.

When an older guide lacks columnFk, opening its settings or loading it
through the Guide Manager adds the attribute with the default true. The guide
root attribute is the saved value.

For T21 manual verification, create or open a skirt guide and open Component
Settings. Confirm Column FK is checked by default, clear it, close and reopen
the settings, and confirm it remains clear. Set the root attribute true and
reopen the settings to confirm the check state follows the guide. Save and
reopen the guide scene with both true and false values and confirm the value
is preserved. The automatic save and reload checks are part of
tests/ymt_skirt_01/test_cut_panels.py.

## Leg profile

The Leg group labels Hip Radius Scale X and Hip Radius Scale Z control the
ringScaleX and ringScaleZ guide attributes. Ring Height Scale continues to
control ringScaleY.

The Leg profile group sets X/Z radius multipliers for the thigh, knee,
calf, and ankle, plus thigh and calf positions along their leg segments.
Radius multipliers default to 1.0 and positions to 0.5. The hip ellipse
remains half the hip separation times ringScaleX/Z; ringScaleY retains
its existing axial meaning. The collision falloff band is relative to
the per-axis local profile radius.

Editing a profile value redraws five preview ellipses per leg: hip,
thigh, knee, calf, and heel. Hip and thigh follow the hip-to-knee axis;
knee, calf, and heel follow the knee-to-heel axis.

Choose the unclothed body in its bind pose using Use selection, or enter a
mesh name or the group that contains the body parts in Body mesh (every
mesh below the group is sampled), then press Fit profile
from mesh. Fitting measures the currently posed mesh in world space,
averages both legs, and updates the hip scales and profile values.
An unmeasurable interior station uses a midpoint fallback with a warning;
a measured side takes precedence over a fallback side. The Script Editor
reports absolute radii and fallback status for each side and station.
Invalid mesh inputs or unmeasurable hip, knee, or heel sections stop the
fit before parameters change. The mesh is only needed for fitting;
building the rig does not require it.

## Wave layer (guide toggle `wave`, default off)

Key or drive the ui-host channels to animate the wave. You can use keys,
expressions, layers, constraints, or utility nodes. The deformer has no
scene-time input or previous-frame state.

Host channels are grouped by prefix: `sway*` = continuous layers,
`send*` = the one-shot wave send.

| Host channels | Use |
| --- | --- |
| `waveAmplitude` | Set the gain for all wave layers (0..3). |
| `swayAmount` | Set the gain for the periodic V and U layers (0..2). |
| `swayVertical`, `swayAround` | Set separate gains for waist-to-hem waves and circumference scallops (0..2). |
| `swayPhase`, `swaySpin` | Advance the V phase in cycles and rotate the U pattern in revolutions. |
| `swayDirectional` | Blend from radial expansion/contraction at 0 to directional sway at 1. |
| `swayDirX`, `swayDirZ` | Set the sway direction. The vector length does not set sway strength. |
| `swaySpread` | Add per-column V phase offsets in cycles (0..0.5). Start with 0.05 to 0.15. |
| `swayNoise` | Add displacement noise (0..2). You can use phase spread with this at 0. |
| `swayNoisePhase` | Change the noise pattern used for displacement and phase spread. |
| `sendAmount` | Fade the send contribution while keeping its direction and position (0..2). |
| `sendDirX`, `sendDirZ` | Set the send vector. Its length retains its contribution to send strength. |
| `sendPos` | Move the send crest from waist (0) to hem (1) and beyond. |

For a new rig, raise `swayAmount` and key `swayPhase`. With the defaults
`swayVertical=1`, `swayAround=0`, and `swayDirectional=1`, you get
directional sway along world -X. Use linear phase tangents for steady
travel; use eased tangents and holds to vary the timing. At complexity 0,
each +1 cycle advances the V pattern by one wavelength. The golden-ratio
secondary travels at a different speed when complexity is nonzero.

For circumference scallops, raise `swayAround` and key `swaySpin`.
Set `swayVertical=0` to isolate that layer. With `waveCountU>0`, each
layer retains the original factor of 0.5; turning one layer off does not
increase the other. Set `swayVertical=2` for a full-strength V-only wave
while keeping `waveCountU>0`. Setting `waveCountU=0` disables the U layer
and removes the V factor of 0.5, as in the previous version.

Sway and send use world X/Z axes by default. Riggers can set
`idleDirectionSpace` or `impulseSpace` to Bell Local on the deformer;
these settings are independent. For world sway, the deformer normalizes
the direction before removing its bell-axis component. Sway weakens as
the chosen direction aligns with the bell axis. A zero direction gives
zero V sway at `swayDirectional=1`.

For a send accent, choose `sendDirX/Z`, raise `sendAmount`, and key
`sendPos` from 0 to `1 + impulseWidth`. At the default width of 0.25,
use 1.25 or higher to move the crest past the hem. The default vector
(-0.5, 0) with `sendAmount=1` gives the previous send strength. Fade
`sendAmount` to 0 to return the crest position for another accent.

New rigs start with `swayAmount=0`, `swayNoise=0`, and `sendAmount=0`,
so the wave has no displacement. Rebuild an old rig with `yddColliders`
to use the new node identities and host defaults above.

## Looping

- Periodic layer: key `swayPhase` with linear tangents over an INTEGER
  delta (e.g. 0 -> 2) and use cycle-with-offset infinity; each +1 is one
  full wavelength at `idleComplexity=0`. Use integer revolutions for
  `swaySpin`. For an exact integer-cycle loop, set `idleComplexity=0`
  and keep the geometry, matrices, direction, gains, and noise pattern
  fixed or matching at the loop ends. You can keep `swaySpread` nonzero
  with a fixed noise pattern. With a nonzero complexity, the golden-ratio
  secondary does not repeat on integer phase cycles.
- Noise layer: the pattern depends on the `swayNoisePhase` VALUE, so a
  loop must return to the same value (ping-pong 0 -> K -> 0, or hold).
  A linear cycle-with-offset does NOT loop the noise.
- For repeated sends, fade `sendAmount` to 0 while returning `sendPos`
  to its starting value.

## Rigger settings

Shape/material settings (wave counts, impulse width, sway/send spaces,
noise frequencies, skew, sharpness, impulse directionality, amplitude ramp)
live on each `*_wave_p<id>_def` deformer node as non-keyable channel-box
attributes, deliberately outside Key All and animation layers.

Use a yddColliders plugin build with the ADR-0006 attributes. With an older
plugin, the component build reports the missing attributes and asks you
to rebuild the plugin. With `postCollision` off, you must handle any
inward wave tucks that enter the legs; you get a warning during build.

`noiseFrequencyU` controls the spatial density of both displacement
noise and phase spread. `noiseFrequencyV` affects displacement noise
alone. Keep `swayNoisePhase` fixed for a fixed phase-offset pattern.

## Evaluation space

The collider, rebuilt surface, ring skin, and surface samples use component-local
object coordinates. The hidden computational surface remains identity in local
coordinates and uses `inheritsTransform=True`, so its DAG world position applies
the component root exactly once. Root motion is applied to the displayed controls,
bind joints, and computational surface. World-space sway and send directions keep
their existing meaning. Root rotation and positive uniform scale are supported.

Rebuild existing rigs with the plugin panel contract. The bundled `yddColliders`
plugin must provide the object-space geometry contract and Wave
`evaluationToWorldRotation` input. Plugins lacking the panel attributes are rejected before component geometry is created.
See
[ADR-0010](adr/0010-component-local-evaluation.md) for the coordinate contract.

## Working limits

The wave uses current geometric coordinates with the shared reference
height. Moving points changes their phase coordinates, while twisting the
surface can move the phase-offset pattern relative to its columns.

Choose a send width that covers enough CV rows. With the default seven
V rows, a narrow crest can disappear between rows; increase
`rebuildSpansV` or widen `impulseWidth`. High frequencies and sharp
waveforms also need more CVs. The plugin does not adjust resolution or
width for you.

Sway uses radial displacement. You can approximate a pendulum
silhouette, but you do not get arc motion or length, area, or volume
preservation. Bell-local height stays constant when the bell axes are
orthogonal; that guarantee does not apply to a sheared bell matrix.
Post-collision decides each point's contact side from the rest shape
(a hidden static copy of its panel surface, `postCollide_p<id>_rest`) and
projects the point onto the leg volumes' support planes, so a raised
thigh pushes the surface up over itself instead of sideways. The
correction is always applied in full; there is no strength channel on
the host. To disable either pass, use the nodes' standard Maya switches:
`nodeState` on the collider (HasNoEffect outputs the uncollided rings)
and `envelope` or `nodeState` on the post-collide deformer.
`postFalloff` is the band outside the legs in which the correction
fades in; inside the legs it is always full. CV correction does not
guarantee a penetration-free interpolated surface.

When retiming, include every animated input that contributes to the
shape: host channels, node settings, ramp children, upstream matrices,
and geometry. An object-level `scaleKey` can leave non-keyable ramp
children behind. See the [scaleKey attribute selection rules](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/Commands/scaleKey.html).
Check Cached Playback with cache creation and restoration on the rig
you intend to use; a test in Parallel evaluation alone does not cover it.

## Maya acceptance tests

To check the settings layout, open a ymt_skirt_01 component settings window
in Maya and confirm the Grid, Leg, Collision, Panels, and Rig groups appear in
that order. Confirm the three hip/ring scale labels and the Leg profile panel
are visible and their values populate from the guide.

Run `tests/ymt_skirt_01/test_cut_panels.py` with Maya 2026 mayapy and `-B`.
The suite creates a fresh scene for each fixture and covers T1–T15 of the
[seam wiring contract](plans/cut-panels-wiring.md); T16 belongs to the plugin
suite and is skipped here. Set `YMT_COMPONENTS_ROOT`, `MGEAR_RELEASE`, and
`YDD_PLUGIN` to override the repository, mGear release, and plugin paths.
Static linting does not establish Maya runtime acceptance.

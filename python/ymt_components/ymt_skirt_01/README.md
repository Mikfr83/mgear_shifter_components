# ymt_skirt_01

Collider-driven skirt component wrapping `yddSkirtBellCollider`. Contracts
live in `adr/` (0001 base, 0002 ring controllers, 0003 two-pass
collision, 0004 wave oscillator, 0005 ring generalization and rig
ergonomics, [0006 directional wave expression](adr/0006-directional-wave-expression.md),
[0007 ydd plugin identity](adr/0007-ydd-plugin-identity.md),
[0008 grid naming and hierarchy](adr/0008-grid-column-major-naming-and-hierarchy.md),
[0009 leg profile and fitting](adr/0009-leg-profile-guide-and-fitting.md),
[0010 component-local evaluation](adr/0010-component-local-evaluation.md),
and [0011 chain-aim cell frames](adr/0011-chain-aim-cell-frames.md)).

Version 0.1.0 requires yddColliders 4.1.0 with yddSkirtSurfaceFit,
yddSkirtBellCollider, yddSkirtCollideDeformer, and yddSkirtWaveDeformer.
The component loads `yddColliders` even when the upstream `colliders` plugin is loaded.
The guide parameters and host channels retain their existing contracts.
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
the surface hem frame. Both cases build and emit a warning so the layout can
be reviewed; controls always sit on their guide positions.

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
both default to 0 and drive the matching `yddSkirtBellCollider` attributes.

Usable ring count is bounded by `rebuildSpansV`: the default four cubic
spans produce seven V CV rows, and the build fails closed if any ring has
no weighted CV row (raise the V spans or widen/move the stations).

## Surface fit and cell tracking

rebuildSpansV sets the yddSkirtSurfaceFit cubic V span count (1..256,
default 4). The output has spansV + 3 V CV rows and preserves the
collider's periodic U structure, whose subdivisions follow bellSubdivision.
The build stops if rebuildSpansV is missing, cannot be converted to an
integer, or falls outside 1..256. The fit approximates the collider surface;
it does not reproduce the previous rebuildSurface output exactly.

Ring anchors sample the fit output before skinning. One uvPin samples
the final surface in component-local evaluation space E for all cells,
with normalizedIsoParms disabled, normalAxis=1, tangentAxis=0, and
relativeSpaceMode=1. UV calibration and column-major indices are unchanged.

Each cell has a multMatrix that computes P = offset × F, where F is its
uvPin frame and offset = M0 × inverse(F0) is constant. A decomposeMatrix
extracts the position p. This preserves the locator rest position and the
contribution of uvPin rotation to position when the rest offset is nonzero.

A plusMinusAverage subtracts the positions of the periodic neighbouring
columns in the order selected by the component winding sign. An aimMatrix
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
orthonormality, offset values, aim enum labels and defaults, aim connections,
rest aim and world matrices, and control identity. These checks precede
ring skin, wave, and post-collision connections. A single warning lists
cells whose locator-to-uvPin rest distance exceeds 0.1 × guide_size in E;
those distances determine how strongly uvPin rotation affects position.
Runtime degeneracy has no fallback or previous-frame retention.

See [ADR-0011](adr/0011-chain-aim-cell-frames.md),
[ADR-0010](adr/0010-component-local-evaluation.md), and the
[local evaluation plan](plans/local-evaluation-and-performance.md).

## Leg profile

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
live on the `*_wave_def` deformer node as non-keyable channel-box
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

Rebuild existing rigs with the plugin major 4 contract. The bundled `yddColliders`
plugin must provide the object-space geometry contract and Wave
`evaluationToWorldRotation` input. A major 3 plugin fails before construction.
See
[ADR-0010](adr/0010-component-local-evaluation.md) for the coordinate contract.

## Working limits

The wave uses current geometric coordinates. Raising part of the hem
changes the height normalization and can move the wave on other parts
of the skirt. Twisting the surface can move the phase-offset pattern
relative to its columns.

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
(a hidden static copy of the collider surface, `postCollide_rest`) and
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

# ymt_skirt_01

Collider-driven skirt component wrapping `skirtBellCollider`. Contracts
live in `adr/` (0001 base, 0002 ring controllers, 0003 two-pass
collision, 0004 wave oscillator, 0005 ring generalization and rig
ergonomics).

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
both default to 0 and drive the matching `skirtBellCollider` attributes.

Usable ring count is bounded by `rebuildSpansV`: the default four cubic
spans produce seven V CV rows, and the build fails closed if any ring has
no weighted CV row (raise the V spans or widen/move the stations).

## Wave layer (guide toggle `wave`, default off)

The wave deformer NEVER self-animates: it reads no scene time. Nothing
moves until the ui-host channels are keyed or driven (any driver Maya
can evaluate is valid - keys, expressions, layers, constraints).

Host channels are grouped by prefix: `sway*` = continuous layers,
`send*` = the one-shot wave send.

- `waveAmplitude` - master gain (0..3).
- `swayAmount` + `swayPhase` - periodic wave. A linear `swayPhase` curve
  travels crests waist -> hem (+1.0 = one wavelength; slope = speed, so
  eases/holds give tame/tsume). `swaySpin` rotates the hem scallops
  (revolutions).
- `swayNoise` + `swayNoisePhase` - hash-lattice noise layer. This is
  also the per-tuft de-sync: raise `swayNoise` so columns stop moving in
  unison; key `swayNoisePhase` to make the noise evolve.
- `sendDirX` / `sendDirZ` - crest direction in WORLD axes (projected
  onto the skirt; switch the deformer's `impulseSpace` to Bell Local for
  waist-frame semantics). Default (-0.5, 0) = front-to-back drift.
- `sendPos` - the crest position (0 = waist, 1 = hem). Keying 0 -> ~1.2
  IS the "wave send"; a crest fully clears the hem at 1 + impulseWidth.

## Looping

- Periodic layer: key `swayPhase` with linear tangents over an INTEGER
  delta (e.g. 0 -> 2) and use cycle-with-offset infinity; each +1 is one
  full wavelength, so the loop is seamless. `swaySpin` loops the same
  way (integer revolutions). EXACT loops require `idleComplexity = 0` on
  the deformer - the golden-ratio secondary is deliberately
  non-repeating; small complexity values give approximate loops.
- Noise layer: the pattern depends on the `swayNoisePhase` VALUE, so a
  loop must return to the same value (ping-pong 0 -> K -> 0, or hold).
  A linear cycle-with-offset does NOT loop the noise.
- `sendPos` sends are one-shot accents, not loop material.

## Rigger settings

Shape/material settings (wave counts, impulse width, impulse space,
noise frequencies, skew, sharpness, directionality, amplitude ramp)
live on the `*_wave_def` deformer node as non-keyable channel-box
attributes, deliberately outside Key All and animation layers.

Wave requires a colliders plugin build that registers
`skirtWaveDeformer`; with `postCollision` off, inward wave tucks are not
leg-corrected (build warns).

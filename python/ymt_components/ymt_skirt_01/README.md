# ymt_skirt_01

Collider-driven skirt component wrapping `skirtBellCollider`. Contracts
live in `adr/` (0001 base, 0002 ring controllers, 0003 two-pass
collision, 0004 wave oscillator).

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

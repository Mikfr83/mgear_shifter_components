# ADR-0004: Deterministic Wave Oscillator - Authored Excitation, Phase-Driven Propagation

Status: Proposed (revision 3 - time-free redesign)
Date: 2026-08-29
Owner: ymtshiftercomponents maintainers
Supersedes: none
Superseded by: none

Revision history:
- rev 1 (2026-08-29): initial contract (time-driven, animCurve delay sampling).
- rev 2 (2026-08-29): design review (Codex high + GLM, Grok adjudication):
  invalidation-range transform, main-thread curve resolution, split V/U
  idle phases, inverted sharpness exponent, bell-local directional dot,
  degeneracy guards, chain-insertion invariant, conformance matrix.
- rev 3.1 (2026-08-29): Maya feel-test amendments - impulse direction is
  interpreted in WORLD axes by default (`impulseSpace` enum, Bell Local
  optional) because the animator thinks in global directions; impulseX
  defaults to -0.5 (front-to-back drift); a hash-lattice value-noise
  layer (`noiseAmplitude`/`noisePhase`/`noiseFrequencyV`/`noiseFrequencyU`,
  theta fed as a cos/sin circle embedding so the U seam never shows) adds
  per-tuft de-synchronization; phase channels carry soft ranges for AE
  sliders; host channels renamed into `sway*` (continuous) / `send*`
  (one-shot) prefix groups for discoverability. With the nonzero default
  send direction, the rest state is no longer a BITWISE no-op: rows
  inside the default kernel support (v < impulseWidth) receive a
  sub-visible offset; the exact-no-op guard still fires whenever the
  summed wave is exactly zero.
- rev 3 (2026-08-29): rigger decision - THE NODE MUST NOT DEPEND ON SCENE
  TIME. All motion comes from keyed attribute values; propagation timing
  is authored via phase/position channels. This deletes the time input,
  propagationTime, the animCurve delay-sampling machinery, the cached-
  playback invalidation transform, and the source-resolution caches -
  the entire complexity cluster the rev-2 implementation review flagged
  (worker-thread plug walks, accepted-graph policing, warning latches).

## Context

ADR-0003 reserved a surface-stage slot between the ring skinning and the
corrective collision pass for a future wave feature. The rigger's goals:

- Anime-style "yuremono" (flowing cloth/hair) expression informed by sakuga
  practice, NOT naturalistic cloth.
- HARD non-goal: simulation. Deterministic and state-independent - the
  same frame always produces the same shape under scrubbing, frame jumps,
  and reverse playback.
- HARD constraint (rev 3): the node must not read scene time. A rig that
  self-animates from `time1` desynchronizes under shot retiming and
  offsets, and forces cache/parallel-evaluation machinery (delayed curve
  sampling, invalidation-range transforms) that the rev-2 implementation
  review showed to be the dominant complexity and risk. Motion enters the
  node ONLY through keyed attribute values at the current frame.

The design discussion analyzed sakuga yuremono practice as three theory
families - pendulum/arc (timing on orbits), wave propagation (root-to-tip
S-curves), and silhouette/design (per-frame shape quality) - with these
rig-relevant conclusions:

1. Pendulum motion is the long-wavelength limit of wave propagation; a
   spatial phase gradient covers both.
2. A skirt is a closed tube: propagation happens in TWO directions -
   V (waist to hem) and U (around the circumference) - as SEPARATE layers
   (vertical wave-sending vs. hem scallops traveling around the rim).
3. Amplitude GROWS toward the hem; at most ~1.5 wavelengths along the
   height; the waveform is an asymmetric anime-S. Injected as defaults
   and shaping, not runtime rules.
4. Propagation parameters are MATERIAL constants, but EXCITATION is a
   PERFORMANCE - authored by the animator, never derived from physics.
   Rev 3 extends this: propagation TIMING is also a performance. In
   sakuga, how fast a crest travels (and where it holds) is drawn, not
   simulated; the rig exposes the crest's position/phase as keyable
   channels instead of applying a fixed automatic delay.

What "wave propagation" means here (rigger question, answered): rev 1-2
implemented it as automatic delay - excitation keys sampled at
t - v * propagationTime so the hem lagged the waist. Rev 3 replaces that
role with two authored mechanisms:
- the periodic layer's spatial phase term (-waveCountV * v): advancing the
  keyed `wavePhaseV` moves crests from waist to hem; travel speed IS the
  slope of the animator's phase curve (tame/tsume by key spacing);
- the impulse layer's keyed `impulsePosition`: the crest's V location is
  keyed directly (0 = waist, 1 = hem), so a "wave send" is
  impulsePosition keyed 0 -> ~1.2 over however many frames the shot wants.

## Decision

### New plugin node: `skirtWaveDeformer` (yamahigashi colliders fork)

An `MPxDeformerNode`, typeId 1274438 (following `skirtCollideDeformer`
1274437), registered in `main.cpp`. Its output is a pure function of
(current-frame input attribute values, current-frame input matrices,
current-frame input geometry). No time input, no animCurve access, no
connection-topology inspection, no internal state (the only mutable
member is a diagnostic warn-once latch, which is not output-affecting).
Scrub / reverse / frame-jump / retime safe by construction; no
transformInvalidationRange or scheduling overrides are needed.

#### Attributes

- `bellMatrix` (matrix, hidden): waistRef worldMatrix, as in
  `skirtCollideDeformer`. Local Y is the cone axis; `globalScale` =
  length of the Y axis row (carries root scale into wave amplitude).
- Master gain: `amplitude` (double, 0..3, default 1), plus standard
  deformer `envelope` and per-point weights.
- Amplitude envelope: `amplitudeRamp` (MRampAttribute created with
  `MRampAttribute::createCurveRamp`; two default LINEAR entries (0,0) and
  (1,1) installed in `postConstructor()`, evaluation status-checked).
  Domain v in [0,1]; default 0 at the waist keeps the root seated
  (sakuga amplitude inversion).
- Periodic layer (standing/traveling wave, off by default):
  - `idleAmplitude` (double, >=0, default 0)
  - `wavePhaseV` (double, keyable, unbounded, default 0): phase in CYCLES
    of the V-traveling wave. +1.0 advances the pattern one full
    wavelength toward the hem.
  - `wavePhaseU` (double, keyable, unbounded, default 0): rotation of the
    U scallop pattern in REVOLUTIONS (signed).
  - `idleComplexity` (0..1, default 0.35): blend weight of the secondary
    golden-ratio components; phi_g = (1 + sqrt(5)) / 2. The secondary
    runs at phi_g times the keyed phases, so a linear phase curve stays
    non-repeating at shot length. Degenerate settings (complexity 0 or 1
    = single tone; constant phase = static pattern) are accepted.
  - `waveCountV` (double, default 1.0, soft max 1.5): S-count along the
    height (the <=1.5 readability rule as a soft limit).
  - `waveCountU` (INTEGER attribute, >=0, default 2): scallop count
    around the circumference; integer by type (U is periodic). 0 disables
    the U layer (and makes `wavePhaseU` a no-op).
- Impulse layer (the animator's "wave send"):
  - `impulseX` (default -0.5), `impulseZ` (default 0) (doubles, keyable,
    unbounded, soft -2..2): horizontal components of the excitation
    vector - the direction the crest bulges, magnitude = strength in
    scene units at globalScale 1. Interpreted per `impulseSpace`.
  - `impulseSpace` (enum, material): 0 = World (DEFAULT - X/Z are global
    axes, projected perpendicular to the cone axis; matches viewport
    intuition and keeps a constant world drift like walk-back flow),
    1 = Bell Local (waist-frame semantics, rotates with the character).
  - `impulsePosition` (double, keyable, soft 0..1.5, default 0): V
    position of the crest center (0 = waist, 1 = hem; >1 runs the crest
    off the hem).
  - `impulseWidth` (double, 0.01..1, default 0.25): half-width of the
    crest in v.
  - `directionality` (0..1, default 0.8): how strongly the U response
    follows the impulse direction.
- Noise layer (per-tuft de-synchronization, off by default):
  - `noiseAmplitude` (>=0, default 0, keyable), `noisePhase` (keyable,
    unbounded, soft -5..5): hash-lattice value noise in [-1,1], sampled
    at (cos(theta)*fU + 7.31, sin(theta)*fU + 3.17, v*fV + noisePhase) -
    the cos/sin circle embedding makes the U seam impossible by
    construction. The pattern depends on the noisePhase VALUE (loop by
    returning to the same value), fully deterministic (integer-hash
    lattice, no tables, no RNG state).
  - `noiseFrequencyV`, `noiseFrequencyU` (material, >=0, default 1.5,
    soft max 5).
- Waveform stylization (periodic layer only; the impulse crest shape is
  the kernel plus the animator's channel curves):
  - `skew` (-1..1, default 0.3): phase distortion phi' = phi +
    skew * sin(phi) (tame/tsume timing; monotone for |skew| < 1,
    2*pi-periodic, seam-safe).
  - `sharpness` (0..1, default 0.3): crest peaking
    S(phi) = sign(sin phi') * |sin phi'|^(1 + 3 * sharpness)
    (exponent > 1: narrow crests AND C1 at zero crossings).
- attributeAffects: EVERY input above, including `bellMatrix` and
  `amplitudeRamp`, must `attributeAffects(outputGeom)`.

#### Per-CV coordinates (computed each frame from input geometry)

In bell-local space (p_local = p_world * bellMatrix_inverse, axis = +Y):

- Degeneracy guard (ADR-0003 policy): if any `bellMatrix` entry is
  non-finite, or |det(bellMatrix)| < 1e-8, or the bell Y axis length is
  < 1e-8, pass the geometry through UNMODIFIED for that frame and emit a
  one-time diagnostic. Non-finite input points pass through individually.
- y_i = height along the axis; v_i = clamp(y_i / y_hem, 0, 1) with
  y_hem = max over CVs, floored at 1e-5 scene units (per-frame, so the
  envelope tracks the collider's dynamic height - see revisit trigger).
- theta_i = atan2(p_local.z, p_local.x) in [-pi, pi], zero at bell local
  +X; r_hat_local_i = normalize((p_local.x, 0, p_local.z)) (skip the
  point below 1e-8 radial length). r_hat_world_i = world bell-radial
  (same construction as `skirtCollideDeformer`'s bellRadialWorld; skip
  when degenerate).
- Output positions written back through the deformer's
  `worldToLocalMatrix`, as in `skirtCollideDeformer`.

#### Signal

Definitions: lerp(a, b, t) = (1 - t) * a + t * b. S(phi) is the
skew/sharpness-shaped sine above. phi_g = (1 + sqrt(5)) / 2.
n = waveCountU (integer).

- Periodic layer, TWO independent phases (separate layers, Context 2):
  - phi_V  = 2*pi * (wavePhaseV - waveCountV * v)
  - phi_U  = n * (theta - 2*pi * wavePhaseU)
  - phi_V2 = 2*pi * (phi_g * wavePhaseV - waveCountV * v) + pi/2
  - phi_U2 = n * (theta - 2*pi * phi_g * wavePhaseU) + pi/2
  - With c = idleComplexity:
    W_idle = idleAmplitude * ( (1-c) * B(phi_V, phi_U)
                             +  c   * B(phi_V2, phi_U2) )
    where B(a, b) = (S(a) + S(b)) / 2 when n > 0, and B(a, b) = S(a)
    when n = 0 (no silent amplitude halving).
  Keying wavePhaseV linearly makes crests travel waist -> hem; keying
  wavePhaseU rotates the scallops around the rim. The two phases never
  couple (the rev-2 helix defect stays fixed).
- Impulse layer: E = (impulseX, 0, impulseZ), CURRENT values,
  interpreted per `impulseSpace` (World: projected perpendicular to the
  cone axis, dot taken against r_hat_world; Bell Local: dot against
  r_hat_local as below).
  Crest kernel (C1, compact support):
    k(v) = cos^2( pi * (v - impulsePosition) / (2 * impulseWidth) )
           when |v - impulsePosition| < impulseWidth, else 0.
  Directional weight in BELL-LOCAL space:
    W_imp = k(v) * ( (1 - d) * |E| + d * (r_hat_local . E) ),
    d = directionality; W_imp = 0 exactly when |E| < 1e-5 (never
    normalize a near-zero vector). The dot is SIGNED: the impulse side
    bulges out; the opposite side (dot = -|E|) evaluates to
    (1 - 2d) * |E|, i.e. it tucks IN only when d > 0.5 (default 0.8),
    is zero at d = 0.5, and bulges out below (C/S alternation requires
    d above one half).
- Noise layer: W_noise = noiseAmplitude * valueNoise(cos(theta) * fU +
  7.31, sin(theta) * fU + 3.17, v * fV + noisePhase), zero below the
  1e-5 amplitude tolerance.
- Displacement: delta_p_i = r_hat_world_i * globalScale * envelope *
  weight_i * amplitude * amplitudeRamp(v_i) * (W_idle + W_imp + W_noise).
  Bell-radial only; local height preserved. Vertical / hem-flip (mekure)
  stays out of scope (revisit trigger).

### Component-side chain (ymt_skirt_01)

- Chain (fills the slot ADR-0003 reserved; its order stands):
  `skirtBellCollider` -> `rebuildSurface` -> `ringSkin_skc` ->
  `skirtWaveDeformer` -> `skirtCollideDeformer` -> surface shape ->
  cell rivets. Ring anchors keep sampling the pre-skin rebuild output;
  the graph stays acyclic.
- INSERTION INVARIANT (cmds.deformer APPENDS): create `skirtWaveDeformer`
  after `ringSkin_skc` and BEFORE `skirtCollideDeformer`, then ASSERT the
  shape's deformer order is skin -> wave -> collide; with `postCollision`
  False assert wave is last. Build fails loudly on wrong order.
- `wave` True with `postCollision` False is allowed but UNCORRECTED BY
  DESIGN (inward tucks can enter the legs); the build warns once.
- The component connects ONLY: waistRef worldMatrix -> `bellMatrix`.
  No time connection exists.
- Animator attributes on the ui host (performance set), grouped by
  prefix - `sway*` continuous layers, `send*` one-shot send - for
  discoverability of the two excitation styles:
  - `waveAmplitude` (0..3, default 1) -> `amplitude`
  - `swayAmount` (0..2, default 0) -> `idleAmplitude` (host range is a
    deliberate performer clamp; node stays >= 0 unbounded)
  - `swayPhase` (unbounded, soft -5..5, 0) -> `wavePhaseV`
  - `swaySpin` (unbounded, soft -5..5, 0) -> `wavePhaseU`
  - `swayNoise` (0..2, default 0) -> `noiseAmplitude`
  - `swayNoisePhase` (unbounded, soft -5..5, 0) -> `noisePhase`
  - `sendDirX` (unbounded, soft -2..2, default -0.5), `sendDirZ` (same,
    0) -> `impulseX` / `impulseZ`
  - `sendPos` (0..2, keyable, 0) -> `impulsePosition` (a crest fully
    clears the hem at 1 + impulseWidth, so the host max covers the
    node's maximum width)
  Material/stylization parameters (waveCountV, waveCountU, impulseWidth,
  impulseSpace, noise frequencies, idleComplexity, skew, sharpness,
  directionality, amplitudeRamp) stay on the deformer node as
  rigger-tuned settings (non-keyable, channel-box visible).
- Any channel may be driven by keys, expressions, constraints, layers, or
  utility networks - the node only reads current values, so every driver
  Maya can evaluate is equally valid. No restriction, no diagnostics.
- Guide parameter `wave` (bool, default False) gates the feature at build
  time, same policy as `postCollision`: when True and the loaded colliders
  plugin does not register `skirtWaveDeformer`, the build raises; when
  False the component builds exactly as ADR-0003.
- `VERSION` stays `[1, 5, 0]` in both `__init__.py` and `guide.py`
  (feature has not shipped between revisions).

## Considered Options

1. Simulation layer (nucleus / jiggle / history-buffer deformer)
   - Violates the hard non-goal: state-dependent, scrub-unsafe.
2. Automatic follow-through derived from root motion
   - Needs prior-frame data = hidden simulation. Rejected.
3. Time-driven propagation: `time1` input + excitation animCurves sampled
   at t - v * propagationTime (rev 1-2 design)
   - Pros: automatic hem lag from a single keyed pulse.
   - Cons (why rev 3 rejects it): the node self-animates from scene time,
     breaking shot retiming/offsets; output-at-t depends on inputs at
     other times, requiring transformInvalidationRange for cached
     playback and main-thread animCurve resolution with accepted-graph
     policing - the implementation review found worker-thread plug walks
     (BLOCKER), accepted-graph over-reach, and a unitConversion bypass in
     exactly this machinery. The authored-phase model deletes the entire
     risk class and gives the animator MORE control (travel speed, holds,
     reversals are keyable), at the cost of having to key the travel.
4. Native node network (per-CV trig plumbing)
   - Node count explodes; no waveform shaping. Rejected.
5. C++ deformer, phase/position-driven pure function (chosen).

## Consequences

The wave layer composes where ADR-0003 reserved it; waves cannot push the
skirt through the legs while `postCollision` is up, and authored inward
tucks facing the legs are flattened by pass 2 BY DESIGN. Cell rivets
carry wave motion in position and orientation; the FK manual layer stays
downstream and uncorrected. The fork gains a third registered node;
per-Maya-version mll rebuilds are required before the `wave` gate can be
enabled.

Animator workflow: raise `waveIdle` and key `wavePhase` (linear = steady
travel; eased/held = tame/tsume) and optionally `waveSpin` for rim
rotation; for a wave-send accent, set `waveImpulseX/Z` direction and key
`waveImpulsePos` 0 -> ~1.2. A rig-facing note in the component docs
should state that nothing moves until these channels are keyed or driven
- the node never self-animates.

Acceptance requires a Maya conformance pass covering: serial and parallel
EM, cached playback, forward/reverse/scrub/frame jumps, retiming a keyed
shot (wave follows the retime exactly), the U seam with integer
waveCountU, degenerate bellMatrix frames, Maya 2022+ with Python
3.7-compatible component build code.

## Confidence and Revisit Trigger

Confidence: Medium

Revisit this ADR when:

- vertical / hem-flip (mekure) expression is wanted - needs a second
  displacement basis.
- a single impulse crest proves insufficient (multiple simultaneous wave
  sends) - add an impulse multi-array or a second impulse bank.
- automatic hem lag is wanted after all - it can be layered ON TOP as rig
  content (e.g. a utility network or keyed offset between two phase
  channels) without reintroducing time into the node; only if that proves
  unworkable, revisit option 3 with its full machinery.
- the per-frame y_hem normalization visibly disturbs the wave (it feeds
  both the envelope and the phase/kernel positions; height changes can
  shift the pattern) - switch the phase/kernel term to a static height
  from the component's cone fit.
- skew/sharpness stylization proves insufficient - move to an
  MRampAttribute waveform profile.
- geometric theta and the component's authored U calibration diverge
  enough to matter, or instances need decorrelated patterns (add a U
  phase origin offset).

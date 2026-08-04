---
paths:
  - "laser_core.py"
  - "task_panels.py"
---

# Photo engraving: the 7 tramages, the nuancier curve, the preview

## The 7 tramages

| # | Name | How grey is produced |
|---|---|---|
| 0 | Diffusion (Floyd-Steinberg) | density of IDENTICAL dots |
| 1 | Durée variable | one dot per cell, pulse duration ∝ darkness |
| 2 | Lignes calibrées | per-pixel S via the measured nuancier curve |
| 3 | Diffusion en lignes | FS dither, fixed-S on/off per pixel |
| 4 | Gros points Z | dot DIAMETER, via per-dot Z (Z moves *between* dots) |
| 5 | Similigravure | AM 45° screen — dot AREA, no calibration |
| 6 | Lignes gravées | line WIDTH, from the measured kerf table, no calibration |

Shared serpentine emitter `_emit_raster_rows` (modes 2, 3, 5, 6). Gamma lives in the panel
(`spn_gamma`, applied in `_build_rows`). `generate_gcode_photo_sampler` is the comparison strip.

**The arc that produced 5, 6 and the split**: the calibrated chain (nuancier → curve → power) asks
the wood to *produce* a grey, and near its burn threshold the grain decides instead. Modes 5 and 6
make grey a **geometry** — a surface, or a width — so no nuancier, no curve, no regime to respect.
Mode 6 is the one the user retained.

## The nuancier curve, and why it kept lying

`darkness_fluence_curve(material)` (defocused tones only, isotonic/PAVA smoothing),
`fluence_for_darkness`, `feed_for_custom_shade` — used by Marquage's "ton sur mesure" and the
calibrated photo modes.

**A tone only feeds this curve if it has BOTH `z_offset > 0` AND `width > 0`** — the width being the
calliper-measured burn line width, which almost nothing sets. Observed on real data (2026-07-29):
83 beech tones, 57 defocused, but only **7 with any width**, so the curve ran on 6 points — and all
6 were judged 100 % darkness (one of them a tone that engraved nothing at all). It returned the
100 % recipe for every requested darkness, silently. **A rich nuancier is NOT evidence this works**:
check `len(darkness_fluence_curve(mat))` and the SPREAD of its darkness values, not the tone count.

**The board that actually feeds this curve is the `noirceur_balayage` objective (v2.5.0)** — flats,
not isolated traces, at ONE feed, one defocus, one pitch, judged by eye. Two design points carry
hard-won lessons: the recorded `width` is **the hatch pitch**, not a calliper reading (in a raster
what governs the energy is how far you advance between passes — getting it wrong is the factor-8
error), and the powers are **deliberately shuffled** on the board, because patches in increasing
order get judged against their neighbours and the eye rebuilds a regular progression that isn't
there (a first series judged that way came back as exact arithmetic progressions with 11 % of pairs
inverted against the real energy order). Selecting the objective pre-fills feed/defocus/width in the
Test-grid panel's own "+ Ajouter ce ton" block — pre-filling beats warning.

### The tone band's numbers were BEECH numbers (v2.75.0)

`noirceur_balayage` engraved the same recipe for every material: S200→S1000 at F2000, defocus 15,
pitch 0.80. On beech that already wasted **3 cells of 10** — the workshop's own nuancier records it:
S195 → 0, S235 → 0, S275 → 2, so nothing marks below ~S300 in that regime. On spruce, 2026-08-04,
**7 of 10 came out blank**: a whole plank burned for three tones.

**His boards said so before the burn.** The measurement grid offers the same cells to every
material, and a cell left empty means there was nothing to measure. On spruce every empty cell sits
in the least-energetic corner — at focus S200 stops after F400 (beech runs to F3000, at 0.03 mm),
S400/S600 stop before F3000; at defocus 15 S200 stops after F400. Beech's same grid is full.

`regime_bande_tons(material, feed, defocus, n)` → `(feed, powers, explanation)` reads that and
fixes two things, in order: the **feed**, pulled back to `vitesse_maxi_mesuree` when the request
lies outside anything observed, then the **power floor** (`puissance_mini_qui_marque`) so the
lightest cell still marks. The panel shows the explanation above the objective's note.

Three points that make it work rather than merely look right:

- **A judged darkness of 0 is a measurement the width table cannot hold.** You don't enter the width
  of an absent trace — you leave the cell empty, and an empty cell is indistinguishable from an
  unmeasured one. So tones are consulted **first**, and only `darkness > 0` counts as evidence of a
  mark.
- **A judged tone also re-opens the FEED**, not just the floor. A defocused width is only measurable
  at the boards' slow feeds (F800 at most), so without this a range-finder board reported in ②
  would change nothing and the objective would clamp to F800 forever.
- **On a never-measured material nothing is recalibrated, and the panel says so** — that first board
  is a range-finder, and its blank cells are its measurement.

`ordre_melange(n)` now carries the shuffle rule (pair `i` with `i+n/2`, evens then odds) instead of
a hand-written list of ten numbers, and **reproduces that list exactly** — `puissances_bande_tons`
is asserted against it. The "no two adjacent ranks side by side" guarantee only holds from n=8
(within a block the gap is `n/2-2`); the band engraves ten, and the docstring says so rather than
pretending otherwise.

**Known and deliberately NOT fixed here**: `_bilinear_burn` **clamps in feed**. Spruce has no
defocus-15 measurement past F800, so `burn_width_defocus_scaled` answers the F800 width for F1200
and F2000 alike — to the centime — i.e. 0.84 mm at S200/F2000, *105 % of the 0.80 pitch, "a fully
covered flat"*, on a cell the wood left bare. The model does not say "I don't know", it says a
number. Un-clamping it would move engravings whose power and coverage Christophe tuned by eye on
wood, so the fix here is a **separate question** — "has this regime been observed at all?" — that
callers who need it can ask.

The Grille de test's `largeurs_defocus` objective (v1.87.0) exists to produce the missing pairing —
measured width AND judged darkness, at the same defocus. A width measured at FOCUS cannot feed this
curve at all (the `z_offset > 0` filter rejects it), which is why Planche 1 — the focus-widths board
— is irrelevant here. **Its feeds must stay SLOW (F200–2000, v1.87.2).**
Defocused, the spot is ~4× wider, power density collapses, and an ISOLATED line stops marking well
before the feeds where light tones live. Shipped first at F1000–4000 → **18 of 25 cells came out
blank on beech**. The deeper consequence is physical, not a tooling gap: on this material, "feeds
slow enough for a measurable line" and "feeds fast enough for a light tone" barely overlap — which
is exactly why every curve point ended up at 100 %. **Expect the light end of the darkness scale to
have no measurable width, and do not widen the feeds to chase it.**

### DARKNESS IS NOT A FUNCTION OF ENERGY ALONE — established experimentally 2026-07-29

Four strips engraved at rigorously identical energy per millimetre (F650/F1000/F1500/F2000 — S scales
with F, so S/F is constant) rendered visibly different darknesses: **slower is darker**. F650
saturated by the 2nd patch where F2000 held to the 6th. **Dwell time matters**, and
`darkness_fluence_curve` — which knows only fluence — is therefore structurally incomplete.

Corollary: a curve built from tones measured at MIXED feeds is incoherent by construction (the
workshop's was: lights at F2000, darks at F650), and no formula fix can rescue it. A curve is only
valid near the feed it was measured at, so `TaskPanelHalftone`'s verdict checks BOTH axes of the
regime — defocus and feed — and the one-click fix corrects both together. **Do not "improve" the
model by adding energy terms without confronting this: the missing variable is time, not energy.**

### Engrave at the SAME defocus the tones were measured at (v1.90.0)

A tighter spot concentrates the same power on a smaller area, and the error goes as the **SQUARE** of
the diameter ratio. Observed: nuancier measured at defocus 15 (spot 1.16), panel set to spot 0.80
(defocus 8.75) → 1.45× smaller spot → **2.1× the power density**, every calibrated photo solid
black, nothing said a word. The trap is that "Largeur du point" silently drives `z_work` through
`defocus_for_spot_diameter`, and it used to sit alone in its own section far from the material and
the pitch. `TaskPanelHalftone` now groups material + spot width + pitch in one "Trait & matière"
section with `_maj_regime()` printing a live verdict plus a one-click fix. The regime half only
applies to mode 2 — the others never read the curve.

### Curve fluence → S uses the MEASURED width of the tone being aimed at (v1.91.0)

`width_for_darkness(material, target)`, never a geometric width. `fluence = P/(width·v)`, so
`S = fluence·width·feed` gives back exactly `P·feed/v`: the energy per millimetre of the tone that
produced that darkness. Verified on the workshop's 6 beech tones within **1.7 %** (residue = S
quantised to steps of 5). Substituting anything else breaks the identity the curve rests on.

The burn width varies strongly with power — 0.40 mm on light tones up to 1.00 mm on blacks, for a
1.16 mm optical spot: at low power only the beam's core crosses the burn threshold. Using the raster
PITCH instead (v1.89.0) made a 10 % target ask for S230 instead of S120 — nearly double the energy,
and the mire came out black over its whole length.

**`darkness_width_points` must be HOISTED out of pixel loops** (both generators do): it reads the
config, and one read per pixel makes photo generation unusable.

`_pas_surfacique(pitch, line_width)` survives only as the FALLBACK when a material has no measured
width at all. Historical note (v1.89.0): the curve is calibrated on ISOLATED lines (3 mm apart, one
pass), but a raster overlaps them — a 0.80 mm burn laid every 0.30 mm passes over each point 2.7×.
Using the width delivered 2.7× too much energy and every calibrated photo came out solid black; both
`generate_gcode_photo_lines` AND `generate_gcode_photo_sampler` did it, **so the mire meant to
validate the calibration was broken the same way**. What governs areal energy is how far you ADVANCE
between lines: `P/(pitch·v)`, so `S = fluence · pitch · feed` and the width cancels out. The `min()`
covers pitch > width, where bare wood is left between lines and the width governs what burns.

## Similigravure — clustered-dot AM screen (v1.95.0, index 5)

Grey is a **surface**: every dot burns at full power, the *diameter* carries the tone.
`core.am_halftone_screen(darkness_rows, k)` → binary grid, then the existing `_emit_raster_rows`
(same emitter as dither-lines) — that reuse is why the whole feature is small. Burns **AT FOCUS**
(`z_work = Z_WORK_MM`, ignoring "largeur du point"): the dot must be crisp, it *is* the grain.

Rational-tangent screening: the cell is spanned by `(k, k)` and `(-k, k)` on the pixel lattice. With
`u = x+y`, `v = y-x` those become `(2k, 0)` and `(0, 2k)` → exact integer arithmetic, **exactly 45°
with no rounding** (hence no moiré), and `2k²` pixels = `2k²` grey levels. Each cell lights its N
pixels nearest the centre, `N = mean darkness × 2k²`, so coverage *equals* the requested darkness —
verified 0→100 % to within one cell pixel. `am_screen_k(spacing_mm, pitch)` /
`am_screen_spacing(k, pitch)` convert between the user-facing mm spacing and k; the panel shows the
spacing actually obtained, since k is rounded.

Two traps if this code is touched:

- **Centre the cell grouping on the lattice points** — note the `+k` in `am_halftone_screen`'s cell
  index. `am_screen_ranks` orders pixels around the cell CENTRE (min-norm representative per residue
  class), while plain floor division cuts cells offset by half a mesh. Mismatched, the tone applied
  to a dot comes from a region half a cell away and the dot smears across the boundary. **Invisible
  by eye** (the render still looked like round dots); caught only by a compactness assertion on one
  cell's lit pixels vs the radius of an equal-area disc.
- **The coverage promise assumes the scan lines touch.** A burn narrower than the pitch leaves bare
  wood between lines: dots come out combed and the whole image lightens by `1 - burn/pitch`,
  silently. On Hêtre at focus F2000 the measured burn is only 0.10 mm. `_update_grid_info` compares
  `core.burn_width_at(power, feed, material)` against the pitch and says so with numbers. That's why
  the material combo stays visible for this tramage even though the nuancier is never consulted.

## Lignes gravées — swelling line (v1.96.0, index 6)

One continuous line per row, beam never cut, whose **width** carries the grey: thin in the lights,
thick in the darks, like a copperplate engraving. Read off the **measured burn widths** (the kerf
table), not the nuancier — so no calibration curve, and no bare wood anywhere (the original complaint
about the calibrated portrait: 27 % of the board unengraved).
`core.swell_power_levels(material, feed, line_min_mm)` → `(S values, w_min, w_max)` is the shared
source for both `generate_gcode_photo_swell_lines` and the preview; it indexes rather than inverting
per pixel, because the width table is a config read.

### The focus-only rule was TRUE, then the remeasure killed it (v2.53.0)

For a long time this burned **at focus**, and only at focus. The reasoning was sound: what matters is
not absolute width but the **ratio** thinnest/thickest, and in defocus the spot is already wide — its
size set by beam geometry, power barely moving it. July's beech table said defocus 36: 1.90→2.60 mm
(1.4×); defocus 15: 0.80→1.30 (1.6×); **at focus 0.10→0.30 (3.0×)**. Case closed.

August's remeasure reopened it. On the current table, **focus at F800 gives only 1.67×**
(0.12→0.20 mm) while **defocus 15 at F650 gives 1.73×** (0.67→1.16 mm) — with a pitch six times
wider, so a sixth of the rows and far less energy. Same trap as the fabricated focus column: a value
frozen into code outlives the measurement that contradicts it. `burn_width_power_table`,
`burn_width_range`, `swell_plage`, `swell_max_feed`, `swell_plafond_suffisant`,
`energie_lignes_gravees`, `swell_refus_message`, `swell_power_levels` and both generators now take
`defocus=0.0`; the generators compute `z_grave = z_work + defocus` themselves, so the width table and
the trajectory cannot describe two different heights.

**Limited to MEASURED levels**, Christophe's explicit call on 2026-08-03: between two levels the model
interpolates, and a level holding one power returns the same width at S200 and S1000 — a 1.00× ratio
nothing on screen would explain. A non-measured height returns `[]` and a refusal that *lists* the
measured levels. Two independent guards enforce it (the level check, and `s_dep` finding no measured
power at that height) — a sabotage of either alone leaves the property standing.

What is traded away is **detail**: a 120 mm portrait is 600 rows at focus/pitch 0.20 and 100 rows at
defocus 15/pitch 1.20. That is the point, not a regression — *"c'est pas le nombre de lignes qui
compte, c'est le style donné au portrait par l'épaisseur de ligne même s'il y a moins de détails"*.

**The regime must be NAMED in the verdict's first sentence.** 0.12→0.20 and 0.67→1.16 mm are the same
wood at the same feed and two unrelated engravings; a range without its height doesn't say which one
it describes.

On the workshop's beech, only **defocus 15** clears `SWELL_RAPPORT_MINI`, and only up to F650 — 36, 40,
55 and 60 top out at 1.49× (F200) and refuse at every feed. Expect that: high defocus is where the
spot size stops answering to power, which is what the original rule got right.

At focus the burn width isn't the spot size, it's *where the beam profile crosses the wood's burn
threshold* — and that point moves a lot with power.

### The width can come from the HEIGHT instead — `fuseau_z` (v2.54.0)

Modulating **power** gives one value per cell, so the width changes in steps of one pitch.
Invisible at focus/pitch 0.20; very visible at defocus/pitch 1.16 — Christophe, 2026-08-03, with a
sketch: *"cela me fait des lignes à étages… je pensais que la tête en Z allait se lever
progressivement, ce qui aurait pour conséquence de grossir le trait progressivement"*. He was right,
and 0.1 → 1 mm is simply not reachable by power at any regime (focus gives 0.12 → 0.20).

`echelle_fuseau_z(material, feed, power_max, line_min_mm)` → `(table, w_min, w_max, avert)`, the
shared source for generator, preview and verdict. Wired into the **spiral only** — one continuous
path, so Z never has a row end to recover from.

Four things hold it together:

- **The Z slope is capped** (`pente_z_max`, `limiter_pente_z`, `FUSEAU_MARGE_Z = 0.5`). Past the axis
  limit LinuxCNC does not refuse — it **slows the whole move** so Z can follow, which changes dwell
  time and therefore darkness, silently. Capping ourselves also *is* the smoothing. The cost is
  **detail**, and it must be announced before burning: `longueur_mini_fuseau` is the number that says
  what the mode can render. On beech: 54 mm of Z course, so a full spindle needs 14 mm of trace at
  F200 and 32 mm at F400 — on a 117 mm image, 8 motifs across, or 3.6.
- **Power follows width** (S ∝ diameter, same model as `puissance_fluence_largeur`), clamped to the
  measured span, and `avert` says where the clamp bites. Without it a 20× wider trace gets 20× less
  energy per mm² — the July spiral came out mottled at the wide end and charred at the thin one.
- **The spiral must be sampled finely along the arc** (`FUSEAU_PAS_ARC_MM = 0.4`), NOT at the radial
  pitch. At pitch 3.4 the default sampling puts a point every 3.4 mm, so the width still changed in
  3.4 mm steps — the very staircase this mode exists to remove. Caught by the test (largest Z step
  12.75 mm on a 36 mm course), never by eye.
- **Rapid transit over bare wood, but ONLY where the Z is flat** (v2.56.0). The first version banned
  it outright, on the grounds that the slope budget is computed for `feed`. True where the head is
  climbing — false outside the image, in the corners the spiral crosses because it runs to the
  half-diagonal: there the Z does not move at all. On a 50 mm image at pitch 1.0 those corners are
  **41 % of the path**, and the ban cost a quarter of the job (56 → 43 min).
- **THE Z MOTION IS ENGRAVING TIME, and it is the mode's dominant cost.** LinuxCNC's `F` applies to
  the *vector*: 0.4 mm of XY with 1.5 mm of Z is a 1.55 mm move, so the engraving advances at 26 % of
  the programmed feed. Measured on the workshop's portrait at 50 mm / pitch 1.0: XY path 6 381 mm,
  **Z path 7 031 mm** — the Z travels as far as the XY, because the spiral crosses the subject 305
  times and each crossing is a full up-and-down. Result: the spindle costs **2.1×** the same spiral
  done by power (43 vs 20 min). That is the price of the look, and it must be quoted, not discovered.
  Lowering the slope limit is NOT the lever: 7.5 → 3.0 buys 13 % of time for a visibly softer image,
  and 1.0 destroys the face. `limiter_pente_z` is not the culprit either — it *removes* 18 % of the
  Z travel the image asks for. Size (time ∝ R²) and pitch are the real levers.
  **Any duration quoted for this mode must come from `estimate_job_time_seconds` on the emitted
  G-code, never from `trace / feed`** — the XY-only figure is 25 to 80 % optimistic.
- **THE PITCH CAPS THE SPINDLE** (`largeur_max=pitch`, passed by generator, preview and verdict). The
  first shipped version let the spindle run to the material's widest measured burn (3.43 mm on beech),
  which forces a 3.43 mm pitch — **34 turns on 120 mm, a sparse dotted spiral**. Christophe, preview in
  hand: *"on est loin de ce que je veux"*. Past the pitch, neighbouring turns overlap anyway: the black
  stops being a spindle and becomes a twice-burned flat. Capping also buys **detail**, because the Z
  course falls with the top width and the minimum spindle length is proportional to it — pitch 3.0 →
  41 mm of course and 5.4 mm minimum; **pitch 1.0 → 9 mm and 1.2 mm**. A cap wider than the
  measurements must not exceed them: the measurement always wins.
- **SAMPLE THE IMAGE FINER THAN THE PITCH, AND AVERAGE A WINDOW** (`spirale_niveaux`, v2.57.0 —
  shared source for generator and preview). The first versions read a darkness grid at *pitch*
  resolution and took the nearest cell: every spiral point falling in one cell got the **same** width,
  so the line advanced in steps of one pitch. Invisible at pitch 0.2, glaring at pitch 1.0.
  Christophe spotted it by comparing against the original: *"il y a un traitement en plus, on voit
  que le trait suit un tracé afin de rendre plus de détail"*. Reading Vertigo's own source
  (`convert-image-to-spiral.ts`) confirms it: it samples at **3 px of arc**, against the image's own
  resolution, and takes the **mean of a square** of `0.8 × (gap + max width)` — not one pixel. Ported
  as: the panel builds the grid `SOUS_ECHANTILLON_FUSEAU = 4` times finer than the pitch, and
  `spirale_niveaux` box-averages `FUSEAU_FENETRE = 0.8 × pitch` through a **summed-area table** (four
  reads per point whatever the window; a double loop would be 25 reads × ~90 000 points). Side
  benefit, measured: the smoothing cuts the Z travel too — 231 → 206 min on the 120 mm portrait.
  Test the panel's grid, not only the core function: §12 stayed green with the panel reverted to
  pitch resolution until a panel-level assertion was added.
- **Vertigo's ribbon is SYMMETRIC about the spiral** — `getOuterDots` places the two edges at
  ±width/2 along the angle bisector. The asymmetry a viewer perceives comes from the sampling
  window being anchored by its **corner** (`getImageData(x, y, w, w)`), so the width at a point
  reflects the image half a window down-right of it. Don't build an asymmetric ribbon to chase it.
- **THE VERDICT MUST SAY THE ENERGY** (v2.58.0). The spindle's verdict spoke of width, Z course and
  detail — never of burning. Christophe engraved on 2026-08-03 at pitch 0.50 / F200 / ceiling S900,
  i.e. an index of **9.0** against his engraved anchor of 6.4 for a solid black, and judged it on the
  wood: *"un peu trop de puissance"*. The panel held the number and stayed quiet, while the row
  tramage's verdict has printed it since 01/08 — two verdicts of one family, one of them informed.
  At the darkest the trace fills the pitch, so the areal energy is exactly a flat's:
  `energie_surfacique(power_max, feed, pitch)`. It also **names the feed that lands on the black
  anchor** (`power_max / (pitch × 6.4)`, F281 here) — a number with nothing to do with it sends the
  reader to a calculator. Note the pitch drives energy as much as the feed does: his 0.50 doubled it
  against the 1.0 I had quoted him at 4.5.
- **A control that does nothing must not stay on screen.** `fond_clair` (bare wood / dotted) is read
  only by the row generator; `_spirale_fuseau_z` never even receives it. The field stayed visible in
  spindle mode and Christophe had set it to "Pointillé dégressif" believing he would get it — under
  his threshold he gets bare wood. Hidden when the spindle is on; §14 asserts both states and that
  the generator still ignores `fond_clair`.
- **THE SPINDLE ALSO RUNS ON ROWS** (v2.59.0), and the angle with it. On 2026-08-03 I had ruled rows
  out because Z would have a turn to recover at each end; his engraving killed the objection — at
  pitch 0.50 the Z course is only 2.5 mm, so the turn costs almost nothing. `points_serpentin` +
  `_rangees_fuseau_z` reuse everything: same ladder, same `fuseau_niveaux_chemin` (renamed from
  `spirale_niveaux` — a "spiral" name on path-generic code misleads), same slope limiter, same
  rapid-transit rule. Only the PATH changes. The turn is deliberately **inside** the point list so the
  slope limiter sees it: that is where Z must recover the most, two neighbouring rows being one pitch
  apart and possibly wanting opposite heights.
- **THE ANGLE ROTATES THE PATH, NOT ONLY THE IMAGE.** Rotating the image alone engraves the subject
  **tilted** with straight lines — the exact opposite of what is wanted (seen on the preview before
  the fix). The correct pair: sample the image rotated by −θ (horizontal rows then cross the subject
  at +θ) **then** rotate the emitted path by +θ (`tourner_points`, re-anchored to (0, 0) per the
  workshop's zero-piece convention). A rotation preserves distances, so the slope limiter is valid on
  either path. The frame (`frame_only`) must use the ROTATED bounding box. The engraved rectangle
  grows — 50×76 → 116×119 mm at 30° — so `_grid_size` reads `_largeur_trame_mm()`, which scales the
  requested width by the bbox ratio: otherwise asking for 120 mm at 45° would shrink the subject by
  1.41 without a word. Restricted to the two spindles, whose path is built point by point; the other
  three raster tramages go through `_emit_raster_rows`, horizontal by construction.
- **The spindle checkbox is SHARED by both tramages and its state is remembered**, so it follows when
  you switch from spiral to rows. Four suites went red on that alone: any test about the
  power-modulated behaviour must uncheck it explicitly, exactly like the power ceiling
  (*"un test ne doit pas dépendre de ce qu'il a réglé hier"*).
- **`couverture_max` — the black must stay made of LINES** (v2.59.1). Christophe, second engraving in
  hand: *"c'est encore un peu trop"* — at an energy of **5.14**, already BELOW his 6.4 solid-black
  anchor. What he was seeing was not power but **coverage**: at pitch 0.50 the thickest trace was
  0.50 too, so neighbouring turns touched and the black lost every trace of line structure (hair and
  jacket flat, while the cheek still showed its strokes). **Lowering S does not fix it** — measured
  from S1000 down to S400, coverage stays at 100 %, because as long as the *measured* burn exceeds
  the pitch (3.14 mm against 0.50 on his beech) it is the PITCH that caps the trace, never the power.
  So a dedicated control was the only way. `largeur_max = pitch × couverture_max`, default 1.0 which
  reproduces the previous output bit for bit. At 85 % the blacks keep 15 % of bare wood between turns
  — the copperplate look he was after. The verdict states the coverage obtained, and at 100 % says
  explicitly that turning the power down would change nothing.
  **Note the anchors do not govern this regime**: 6.4 / 13.2 were measured on rows at focus with
  0.2 mm traces. Three boards now say the useful target under the spindle is lower.
- **THE PREVIEW IS FAITHFUL; WHAT DIFFERS IS THE BURN HALO** (settled 2026-08-03). Christophe:
  *"je ne le trouve pas fidèle au résultat"*, then, after looking again: *"c'est les brûlures des
  traits qui m'ont mis en défaut"*. Measuring first was what saved this: the suspicion fell on the
  tone model, and the tone model is **right** — every spindle level is painted at 1.00, pure black,
  so the grey comes entirely from coverage, exactly as on the wood. "Fixing" it would have broken
  what worked. One real but small defect did turn up on the way (the thumbnail's one-pixel floor,
  v2.59.2, +7.6 % → +4.0 % of ink).
  **Do NOT paint a fake halo.** Its width depends on air assist — the workshop's own unrecorded
  variable (*with air: brown halo; without: clean, but the lens fouls faster*) — so any halo drawn
  today would be an invented number dressed as a prediction, the "fabricated table" trap. It becomes
  modellable the day a board is rectified with the halo measured against the trace, at both air
  settings. Note also that the halo fills the lights, so it darkens the real piece relative to the
  preview: part of "c'est encore un peu trop" may be halo rather than coverage.
- **`white_threshold = 0` for this look.** The threshold cuts the beam in the lights, which breaks the
  spiral into dashes — the opposite of the reference, where the line never breaks and the lights are
  merely thin. It is the original "jamais de bois nu" intent, and here it is the right one.

Intermediate heights are **not** measured levels, and that is deliberate here — unlike the fixed
defocus of the row tramage, where an unmeasured height gives a mute regime nobody could explain. The
Z sweeps by construction; the **anchors** stay measured.

`_largeur_defocus(table, …)` is `burn_width_defocus_scaled`'s body on an already-loaded table: the
ladder bisects hundreds of heights, and going through the public function would reload the config
each time — the same defect that made the photo panel take 14 s to open.

Verify the slope on the **emitted G-code**, never on the function that produced it. Size the
tolerance on coordinate rounding (4 decimals → the *length* error dominates the *height* one, and a
tolerance set on dz alone is too tight and goes red on rounding).

### Report the coverage SPREAD, not the ratio

`min(1, w_max/pitch) - w_min/pitch`, not `1 - w_min/w_max`. The ratio is pitch-independent, so the
verdict sat frozen at "56 %" while the preview visibly darkened as the pitch shrank (user caught it:
*"malgré que je change le pas il est toujours à 56 %, pourtant je vois la photo noircir"*). The
spread peaks **exactly at pitch = w_max** and falls off both sides: above it the darks never reach
100 %, below it they already are, so only the lights darken. Hêtre F800 (0.10→0.30): 67 points at
pitch 0.30, but 50 at 0.40 *and* 50 at 0.20. `_verdict_au_foyer` reports the real spread, names the
optimal pitch, and only turns red when the loss exceeds 20 % of the achievable maximum — a suboptimal
pitch is a trade-off, not an error.

### THE VELOCITY BEFORE THE PITCH (v1.97.0)

The feed cliff is not a cliff, it's a slope, and that is the trap of this mode:

| Feed | Line | Ratio | Contrast at pitch 0.30 |
|---|---|---|---|
| F200–**F800** | 0.10 → 0.30 mm | **3.0×** | **67 points** |
| F1000 | 0.10 → 0.23 mm | 2.3× | 43 points |
| F1200 | 0.10 → 0.17 mm | 1.7× | 24 points |
| F1500+ | 0.10 mm, flat | 1.0× | refused |

**The F1500-is-flat row above is the 2026-07 measurement, and the 2026-08-01 board contradicts it
— weakly.** Measured on the rectified photo chain: F1000 reads **0.14 for every power from S200 to
S1000** (five identical values), F1200 0.13–0.14, F1500 0.10–0.13, F3000 0.09–0.13. The column is
no longer *exactly* flat, so `swell_power_levels` stops refusing and `swell_max_feed(Hêtre)` jumps
**800 → 3000**, offering a 1.30× ratio at F3000.

Treat that 1.30× as **noise, not contrast**: the rectified image is 0.02 mm/px and a click is worth
~1 px, so 0.13 vs 0.10 is one and a half pixels. A column reading the same value at five different
powers is the signature of a quantity below the measuring floor, not of a physical plateau with
structure. **Answered in v2.27.0**: `SWELL_RAPPORT_MINI = 1.5` — `swell_power_levels` refuses
below that ratio instead of only when the range is *exactly* flat. On the workshop's fresh beech
this restores `swell_max_feed` to **800** (F1000 1.00×, F1200 1.08×, F1500 1.30×, F3000 1.44× all
refused; F200/F400/F800 at 3.00× all pass). 1.5× sits far from the noise while keeping every regime
that ever worked — F1200 measured 1.7× in July.

**`swell_max_feed` must use the SAME criterion**, and did not for the first minute of that change:
the refusal read *"descendre à F3000"* while F3000 was itself refused. A message and a verdict that
contradict each other are worse than no message. `tests/test_lignes_gravees.py` §19 freezes it — the
feed the refusal names must itself be accepted.

The first portrait engraved in this tramage was burned at **F1000 at pitch 0.30** — a third of the
range lost, and "pas concluant du tout". The panel refused nothing (the range wasn't flat) and its
advice targeted *the pitch* ("contraste maximal au pas 0,23"). Exact, and yet misleading: that advice
is computed on the range measured **at the requested feed**, so following it would have aligned the
pitch to an already-amputated range while the pitch was fine and only the feed needed slowing.

Hence: past `swell_max_feed(material)`, `_verdict_au_foyer` names that feed and quantifies what
you'd recover, **before** any advice about the pitch — and stays silent at fine pitches where slowing
gains nothing (at pitch 0.20 both F800 and F1000 already saturate).

### Two more constraints the panel enforces

- **Feed changes nothing below F800** (0.10→0.30 identical at F200, F400 AND F800 — take the
  fastest), but **from F1500 the width is flat** at 0.10 whatever the power: `swell_power_levels`
  returns None, the generator refuses, and the panel says so rather than emitting uniform lines.
- **Never sample below the lowest MEASURED power.** `burn_width_at` clamps to the measured grid, so
  S0 reports a 0.10 mm line when it burns nothing at all — a mode promising an unbroken line must not
  pick a power it knows nothing about. `burn_width_power_table` starts at the lowest measured S (S200
  on Hêtre). Caught by a test asserting `min(levels) > 0`, not by eye.

### The lowest level is NOT "nothing" — white burned grey (v2.6.0)

The constraint just above has a consequence nobody drew until a board showed it: since level 0 is the
lowest **measured** power (S200 on beech → 0.10 mm), a pure-white pixel engraved a real 0.10 mm line.
At pitch 0.30 that is **33 % of the wood burned to represent white**, and the mode's own G-code header
had been announcing it all along — `(Trait : 0.10 a 0.30 mm -- couverture 33 a 100 %)`. Nothing
consumed that number. Christophe caught it mid-job on 2026-07-31: a white background coming out
uniformly grey.

The mode was deliberately built with `seuil_blanc=False`, answering his earlier complaint that the
calibrated portrait left 27 % of the board unengraved. **That reasoning was over-applied**: those 27 %
were *holes in the mid-tones* — the wood failing to mark where it should have. Leaving the actual
white background bare is the opposite, and is what "white" means. Don't conflate the two again.

`swell_niveau(darkness, n, white_threshold)` → level index or **None** (bare wood) is now the shared
source for the generator AND the preview, exactly like `swell_power_levels`. Default `0.0` reproduces
the original behaviour bit for bit, so the "beam never cut" promise still holds where it is wanted —
`tests/test_lignes_gravees.py` §7 still asserts *no G1 at S0* on a threshold-free call.

Two things worth knowing before touching this:

- **Motion stays continuous.** `_emit_raster_rows` already merged S0 runs into the same sweep, so a
  white gap inside a row becomes `G1 … S0` at the same feed — no `G0`, no stop. With M67 on (the
  user's config) it is `M67 E0 Q0` + `G1`, and the queue is never drained. The threshold *reduces*
  the number of power changes, so it can only help the M67 problem, never worsen it.
- **The threshold is a step.** Below it, bare wood; above it, the line appears at once at
  `w_min/pitch` coverage. On a pure-white background that is exactly right; on a soft gradient into
  the whites it puts a visible contour. Hence the second option below.

### `fond_clair` — filling the step with a dotted line (v2.7.0)

`swell_niveaux_grille(darkness_rows, n, white_threshold, fond_clair)` is the shared grid builder
(generator AND preview) — the dotted decision depends on the cell's **position**, so it cannot be
taken cell-by-cell outside the grid, which is why this replaced the per-cell call.

- `"nu"` — bare wood below the threshold (the v2.6.0 behaviour).
- `"pointille"` — the **thinnest** line (level 0), made intermittent with a duty ratio of
  `d / seuil`, ordered-dithered through a Bayer 4×4. Coverage then sweeps continuously from 0 to
  `w_min/pitch` instead of jumping. **This is the only way below the mode's floor**: the width
  cannot go lower, since the width table stops at the lowest measured power.

Deliberately **ordered**, not error-diffused: `tests/test_lignes_gravees.py` §10 asserts this tramage
never calls `floyd_steinberg_dither`, and an ordered matrix is deterministic, doesn't bleed between
rows, and costs nothing per pixel.

**The remap that makes the join exact.** `swell_niveau` now maps `[seuil, 1] → [0, n-1]` instead of
`[0, 1] → [0, n-1]`. Without it a threshold of 8 % left levels 0–19 unusable: the lightest engraved
cell came out at 0.116 mm instead of 0.10, wasting part of the measured width range *and* leaving
5 points of coverage between the dotted branch (which tops out at `w_min/pitch` = 33.3 %) and the
continuous one (which restarted at 38.6 %). Measured after the fix: 33.3 % on both sides of the
threshold. At `seuil = 0` the remap is the identity, so files engraved before it stay reproducible —
§14 asserts exactly that.

### A GREEN verdict must never describe a defect (v2.7.1)

The zero-threshold warning shipped in v2.6.0 under a green ✓. On 2026-07-31 Christophe sent back a
preview whose whole background was a uniform grey line texture, asking "is this what I'm going to
get?" — and the panel had been spelling out the reason, in words, under a tick that said everything
was fine. Nobody reads a warning beneath a ✓.

Reproduced exactly by rendering the preview at `white = 0`; his saved setting was 5 %, and at 5 %
the same image renders as clean bare wood. So the picture was never the dotted mode misbehaving —
it was the threshold still at zero, which also makes the `fond_clair` selector inert (it greys out,
but a greyed combo still *reads* as active). `_verdict_au_foyer` now returns `False` there, so the
verdict goes red, and says the selector has no effect at a zero threshold.

**Rule to carry:** when a verdict has words for a problem, it must also have the colour for it. A
message and a status that disagree are worse than no message — the reader believes the status.

### The width table knows nothing about DEPTH — `power_max` (v2.8.0)

Found at the bench on 2026-07-31, mid-job: at full power on beech at F800 the trace does measure
0.30 mm, but it **digs** — the surface comes out ridged rather than marked. The kerf table only ever
recorded WIDTH; depth was never measured and cannot be inferred from it. So this is a hand-set
ceiling, not a computed one, and it belongs to the same family as "darkness is not a function of
energy alone": a physical variable the model simply doesn't carry.

`swell_power_levels(..., power_max=)` filters the table to measured points at or below the ceiling —
it never interpolates a new width. Everything downstream (generator, preview, verdict, contrast)
reads that one function, so capping is felt everywhere at once. Cost on beech F800 at pitch 0.30,
measured: S1000 → 0.30 mm / 67 points of contrast; **S950 → 0.29 / 62**; **S900 → 0.28 / 58**;
S800 → 0.25 / 50. Modest at 90–95 %, which is the useful range.

`swell_refus_message(material, feed, power_max)` gains a first branch: a ceiling below the lowest
measured power leaves no span to swell in, and the message must blame the **ceiling**, not the feed —
otherwise it names a perfectly good feed as the culprit.

**Watch out when measuring this from G-code**: the header comment itself contains `S1000` (as in
"90 % de S1000"), so a naive `\bS(\d+)` sweep reports the ceiling leaking. Skip comment lines. That
false alarm cost a round trip here; `tests/test_lignes_gravees.py` §17 carries the helper that avoids
it.

#### Darkness SATURATES near S900-950 — measured twice, 2026-07-31

The v2.8.0 ceiling was introduced as a quality/contrast trade-off. Two independent measurements now
say the contrast half of that trade is largely **theoretical** on this wood:

1. **Twin portraits.** The same 401 × 602 px image engraved at 100 % and at ceiling S900 — G-code
   geometrically identical (25 437 mm burned, 29 602 mm travel), only the power scale differs (mean
   S748 → S680). Measured on a single photo of both boards side by side, normalised by a **local**
   white point per cell: overall darkness essentially equal (0.710 vs 0.702), but the **deep blacks
   are denser at S900** — 10th percentile 0.178 → 0.153, area below 0.30 luminance 20.4 % → 22.6 %,
   against a noise floor of 0.003 read off the upper percentiles.
2. **A 10-patch board** (`noirceur_balayage` geometry, but at FOCUS, F800, pitch 0.30, powers
   S600–S1000 shuffled), ranked by eye. The ranking is **perfect at the group level** — the four
   highest powers take the four darkest slots, then the next pair, etc. — but inside the top group
   **5 of 6 pairs are inverted**: S925 judged darkest, ahead of S950, S975 and S1000.

Alone the second is worth 17 % by chance (4 items). Together with the first, which is independent
and instrument-based, the direction is settled: **above ~S925 you dig without darkening.**

Practical consequences, both encoded: the ceiling tooltip now carries this measurement instead of
presenting the cap as a pure loss, and **92 % is the retained setting on beech at F800**. The eye's
resolution on this material is ~75 S — all 7 of the 45 ranking inversions are between neighbours
25–50 S apart — so there is no point tuning the ceiling finer than that.

**This is per material and per feed.** Re-burn the patch board before carrying the number to another
wood. And note what it does NOT say: nothing here measures depth, so the ceiling remains a hand-set
knob, not a computed one.

### Size matters too — a bench judgement, not a measurement

The three **grain** tramages (4, 5, 6) render grey by the shape of a mark visible to the naked eye,
so there must be enough marks across the subject for the pattern to disappear behind it. The failed
portrait was 80 mm wide and the grain read louder than the face. `_update_grid_info` says so below
100 mm. This one is not measured — it's the user's own conclusion from an engraved board, which on
this project outranks a formula.

## Aperçu photo — rendering the result

The **reverse** of photo mode: paint what the engraving will look like. Lives entirely in
`task_panels.py` (QPainter is Qt). Each burn is drawn as a thick stroke at its **burn width**
(`burn_width_defocus_scaled`, else the optical spot) and a **tone**; strokes composite with
`CompositionMode_Multiply` on a wood background so overlaps deepen. `_render_engraving_photo(strokes)`
→ QImage, `_show_image_dialog` shows it + PNG save. `_strokes_from_operation(op)` maps a combined-job
operation dict so `TaskPanelCombined` renders a whole job at once. Hachures is a geometry mode (no
power/feed) → no preview.

Tone is the **measured nuancier darkness first** (`_tone_measured` → `core.darkness_at`: shades
grouped by measured defocus level, nearest level to the requested defocus, then the same bilinear
S-linear/F-log interpolation as burn widths via `_bilinear_burn(..., key="darkness")`; the material
comes from the panel's own "Nuancier matériau" combo), with the theoretical `_tone_burn` (areal
fluence `P/(width·v)`, saturating `1-exp(-3·f)`) as **fallback**.

An earlier prototype used peak irradiance `P/(spot²·v)`, but it penalised defocus far too hard — a
real MDF burn at S865 F600 defocused 36 mm comes out **dark, not pale** — so the fallback was
**recalibrated on a real engraving** to areal fluence. It still badly overestimates LIGHT tones (MDF
S400 F2000: 5 % measured vs ~55 % predicted — the "light fill renders black" bug), which is why
measured data wins whenever it exists.

**Photo mode got the same preview in v1.94.0** — `TaskPanelHalftone._render_photo_preview(darkness,
largeur_px)` → `(QImage, note)`, feeding BOTH the in-panel thumbnail and the full-size button, so the
two can never disagree. Each tramage is painted **the way it burns**. Before this,
`_update_halftone_preview` treated everything except "Durée variable" as Floyd-Steinberg — the
calibrated-lines mode, which engraves continuous modulated greys, was shown as black/white dots, and
a portrait was burned with no warning its mid-tones were far too light.

Two rules make this preview trustworthy, both worth preserving:

- **Never re-implement the S conversion.** The calibrated-lines path calls
  `core.photo_line_power_fn(material, pitch, line_width, feed, white_threshold)` — the *same* factory
  `generate_gcode_photo_lines` uses — then inverts it via `core.photo_line_tone_table(puissance)`
  (sampled on `puissance` itself, never on a parallel formula) to get the darkness actually obtained.
  That inversion surfaces the two losses a "requested darkness" histogram hides: pixels under the
  white threshold (bare wood) and shadows clamped at `S_MAX` (collapsing to one black). Both are
  reported in the note. `core.zdots_marks(...)` plays the same shared-source role for mode 4, and
  `core.swell_power_levels(...)` for mode 6.
- **A clamped measurement is not a measurement.** `core.darkness_at` bounds to the measured grid and
  returns the edge value **silently**. Dot tramages burn micro-lines whose feed comes from the *pulse
  duration* (F200–1200 on Hêtre), while the nuancier was measured F650–2000 → every dot came back at
  22 %, a perfectly flat photo that looked like data. `core.shade_feed_range(material, z_offset)`
  (same nearest-defocus-level selection as `darkness_at`) now gates it: outside the measured span the
  WHOLE render switches to `_tone_burn` and the note says so — same rule for every tramage, whether
  or not the flatness would have been visible.

### The combined-job preview painted the THEORETICAL tone (v2.71.1)

`_strokes_from_operation` called `_tone_burn` in all five of its branches, while every single-mode
preview goes through `_teinte_gravure` (measured first, theory as fallback). The material already
travelled that far — it was only ever used for the **width**.

**What hid it for months**: on dark settings the two formulas agree within a few points (beech
S900/F200 defocus 15: 94 % measured vs 100 % predicted; MDF S1000/F800: 96 vs 100). The gap only
exists in the **lights**, and there it is enormous — **MDF S400/F2000: 5 % measured against 93 %
predicted, eighty-eight points**. A preview that lies on half the scale looks right. Christophe:
*"c'est pas du tout un ton clair mais bien noir que l'on voit"*.

A test for this must first **prove it has a discriminating case**: on a dark setting any code passes.
`test_apercu_combine.py` §1 searches the workshop's own nuancier for a light setting where measured
and theoretical differ by more than 30 points, and refuses to run if it finds none.

The gradient branches got the same treatment: a width gradient is also a **darkness** gradient, since
the nuancier is measured per defocus level.

### `_bilinear_burn`'s hole-filling must weigh both axes (v2.2.3)

Shared by widths and darkness. On a cell with no measurement it falls back to the nearest neighbour,
and that comparison used the tuple `(|ΔS|, |ΔF|)` — **lexicographic, so power outranked feed by any
margin whatsoever**. Widths barely noticed (their grids are near-complete: 1 hole on beech, 0 on MDF
— the fix moves no width at all). The nuancier fills in tone by tone and is 44 % holes at focus on
beech, where the *only* S1000 tone was measured at F6000: `darkness_at` answered **42 % at every feed
from F400 to F6000**, and S1000 came out lighter than S800. The user's S1000/F800 focus square at
pitch 0.26 came off the machine **carbonized** against that announced 42 %. Both axes are now
normalised by their measured span, in the interpolation's own geometry (S linear, F log).

The wider lesson: a ragged grid is not the same object as a sparse one. `shade_feed_range` reports
the min/max feed over **all** tones, so it called F800 "inside the measured span" while the answer was
a nearest-neighbour guess borrowed from a point 7.5× away in feed. **Coverage per power column is what
matters, and nothing measures it yet.**

Perf: two cell caps, because the surfaces have different budgets. `_VIGNETTE_MAX_CELLS = 20000` for
the thumbnail (recomputed on every settings change) vs `_PREVIEW_MAX_CELLS = 250000` for the button
(explicit click, wait cursor). Painting 250k marks into a 240 px thumbnail cost up to 1.8 s for a
result where ten marks land on one pixel. `_teinte_gravure(..., cache)` memoises on rounded args —
`darkness_at` re-reads the config on every call, so an un-memoised tone lookup inside a per-mark loop
is the same catastrophe as a per-pixel config read in a generator.

## A fabricated table is worse than an empty one (2026-08-01)

The beech focus table was re-measured with the new profile tool. Comparing it against the
morning's backup settled a question nobody had thought to ask: the **old F200, F400 and F800
columns were three identical ramps**, 0.10 → 0.30 by steps of exactly 0.05. Real calliper
readings do not land on five equal steps three times over. That column was never measured, and
everything built on it inherited the fiction:

- two shipped recipes used `pitch: 0.30` "because the trace is 0.30 mm at S1000/F800" — the real
  trace is **0.18 mm**, so they left 0.12 mm of bare wood between every line, 40 % of the
  surface. They engraved stripes;
- the docstring of `swell_power_levels` cited that 0.30 as a bench observation;
- `test_recettes_photo` froze `pitch 0.30 / F800 / 67 points` as literals, so it guarded the
  fiction instead of catching it.

An empty table refuses and sends you to the bench. A fabricated one answers, plausibly, forever.
**When a stored table is suspiciously regular, distrust it before trusting anything derived from
it** — and prefer asserting a *relation* recomputed from the measurements over a literal copied
into a test.

Under the workshop's hand-set ceiling **S900**, the only feeds where beech really swells are
F200 (1.94×) and F1000/F1200; **F800 now refuses**, correctly. `swell_plage(material, feed,
power_max)` is the single source for that judgement.

## The decision and its explanation must read the same numbers

`swell_power_levels` refused **under the power ceiling** while `swell_refus_message` explained
**without it**, so the panel printed *"soit 1.50x -- sous le rapport 1.5x"* — a sentence that
contradicts itself — and then advised *"Descendre à F3000"*, a feed 3.75× **faster** than the one
in use, whose traces are thinner. Three defects, one cause: two code paths answering one
question.

`swell_plage` now computes the range once; `swell_max_feed(material, power_max)`,
`swell_plafond_suffisant` and `swell_refus_message` all read it. When the ceiling is what blocks,
the message says so and names the **lowest** ceiling that unlocks (interpolated, e.g. S925 — not
the measured step above). §20 and §21 of `test_lignes_gravees.py` freeze both properties,
including that the verb matches the direction of the advised feed.

**The same defect came back through the `defocus` argument on 2026-08-03**, in the same function: two
of `swell_refus_message`'s calls (`swell_plafond_suffisant`, `swell_max_feed`) were left without it,
so a refusal at defocus 15 advised *"Passer à F3000"* — the FOCUS answer — and quoted, in the same
sentence, F3000's ratio *at defocus 15*: 1.00×, itself refused. The right answer was F650. Adding a
regime argument to this family means threading it through **every** call inside the explanation, not
only the decision. `swell_max_feed` also had to enumerate the feeds measured **at that level**: beech
is measured at F1200/F3000 at focus and at F600/F650/F1100/F1550 at defocus 15, so scanning the focus
list proposed feeds never measured up there and missed the ones that were. §27 of
`test_lignes_gravees.py` freezes the property over every level, not just focus.

## Measurement margin is not burn margin (2026-08-01, engraved)

The same gradient, engraved twice side by side on beech: **F200 pitch 0.34 carbonised the wood;
F1000 pitch 0.14 came out a clean black.** F1000 also runs twice as fast, so it wins outright.

The shipped recipe had been moved to F200 and called *"le plus sûr"* on the grounds that it had
the largest ratio (1.94×) above the **measurement** floor. That conflated two different safeties.
A wide trace at low feed is wide largely *because the dwell is long*, and dwell is what burns.
Reasoning that ranks regimes from a width table will keep making this mistake — it has now made
it twice in one session.

The workshop already had the number that predicts it. `energie_surfacique` = S/(pitch × F), used
by filled engraving since the carbonised square of 30/07, gives **5.7×** the most economical
measured black at F200 and **2.8×** at F1000. It was simply never shown on this tramage, whose
verdict spoke only of contrast and coverage — two ways of looking at *width*.

`energie_lignes_gravees` now feeds that line into the "Lignes gravées" verdict.
`SEUIL_ENERGIE_LIGNES_GRAVEES = 4.0` is deliberately **not** the filled-engraving threshold (2.0):
that one would cry wolf on F1000, the regime the wood just certified. 4.0 sits between the two
engraved anchors, and both anchors are printed in the message — a threshold you cannot trace back
to wood reads as a caprice. It is a two-point threshold, not a curve; tighten it when a third
board gives a third point.

§22 and §23 of `test_lignes_gravees.py` freeze it: the burning regime must cost more than the
working one, the threshold must fall **between** them, and no shipped recipe may start above it.

## `burn_width_at` re-reads the config on every call

Not a cache miss — there is no cache. `burn_width_at` → `load_burn_widths` → `load_config` →
`json.load` opens and parses the whole config file, every single call. That is fine when
something asks for one width; it is ruinous when something samples a curve.

Two v2.36.0 additions did exactly that, and on 2026-08-01 the **Gravure photo panel took 14
seconds to open with the fan spinning** — Christophe heard the machine, no test noticed:

- `burn_width_power_table` sampled 161 points through `burn_width_at`, though it had already
  loaded the measurements two lines above. It now calls `_bilinear_burn(mesures, …)` directly.
- `swell_plafond_suffisant` rebuilt a whole table **per candidate ceiling** — 161 tables, ~26 000
  config reads for one call. It now builds the table once and scans it; the ratio is monotone in
  the table index, so a single pass is the same answer.

**14.17 s → 0.12 s** to build the panel (118×), and `test_recettes_photo` fell from 16.7 s to
1.1 s as a side effect — the suite had been paying it too, silently.

§24 of `test_lignes_gravees.py` counts `load_config` calls rather than seconds: a wall-clock
threshold is noise on a shared machine, a counter is not. One table, one read.

Anything that samples a width curve must load the measurements **once** and work on the list. If
you find yourself calling `burn_width_at` in a loop, that loop is a file-parsing loop.

## A cell below the wood's own grain noise is not a pale tone (2026-08-02)

The first real tone board read two cells at **1 %** and **3 %**. Christophe looked at the wood:
both were **blank**. The reading was not wrong — it was grain.

The floor is measured, never chosen. `reperes_candidats` already yields the gaps between cells,
which are untouched wood all over the board; reading them gives the grain's own spread. On that
board, 25 such zones read **0.0 → 9.8 %** (mean 3.6, σ 2.2) while the eight palest cells read
**1.1 → 5.1 %** — entirely inside it.

`plancher_bruit_bois` returns **mean + 2σ** (8.1 % there), not the maximum: one reflection or one
knot would carry the maximum, and the floor with it. Cells below are shown as **"—"**, not "0", and
are **excluded from the versement** — a cell the laser did not mark is not a tone of zero, and the
two read differently at the bench.

Verified against his eye: the ten cells the floor rejected are the ten he calls blank. The two
borderline ones (S520 at F3280 and F4000) sit just under it, and he judged them *"quasi zéro,
pas utile"* — so the floor is where it should be. **Don't tune it finer than the wood can
distinguish.**

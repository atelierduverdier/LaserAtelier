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

The Grille de test's `largeurs_defocus` objective (v1.87.0) exists to produce the missing pairing —
measured width AND judged darkness, at the same defocus. `largeurs_foyer` cannot: a width measured
at focus is rejected by the `z_offset > 0` filter. **Its feeds must stay SLOW (F200–2000, v1.87.2).**
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

Burns **at focus**, which is counter-intuitive — the fat lines the power/speed ramp records in defocus
(up to 2.60 mm) are useless here. What matters is not absolute width but the **ratio**
thinnest/thickest; in defocus the spot is already wide, its size set by beam geometry, and power
barely moves it. Measured on Hêtre — defocus 36: 1.90→2.60 mm (1.4×); defocus 15: 0.80→1.30 (1.6×);
**at focus: 0.10→0.30 (3.0×)**. At focus the burn width isn't the spot size, it's *where the beam
profile crosses the wood's burn threshold* — and that point moves a lot with power.

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

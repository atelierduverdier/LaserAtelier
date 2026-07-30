---
paths:
  - "laser_core.py"
---

# G-code generation contract, defocus model, fonts

Generators are `generate_gcode_*(...)` in `laser_core.py`, each returning a **sanitized G-code
string or `None`** (None = empty geometry).

## Dialects — never emit machine literals directly

**Three dialects** via the per-laser-profile setting `gcode_dialect` (`GCODE_DIALECT`, default
`"linuxcnc"`): `_apply_settings_config` derives everything — for `"grbl"`/`"grblhal"` it empties
`SPINDLE_SELECT`, swaps `CMD_ARM` to the M4 (laser-mode) variant, and `cmd_path_blend()` returns
None instead of `"G64"` (they blend natively via `$11`). `cmd_tool_comp()` becomes a comment for
`"grbl"` only; `"grblhal"` keeps T/M6 + G43 H (tool table compiled in, `N_TOOLS`).

**Never emit `$n` / `T`/`M6` / `G43` / `G64` literals** — always go through `SPINDLE_SELECT` /
`cmd_tool_comp()` / `cmd_path_blend()`. The mixed mill+laser offset-test generator is knowingly
LinuxCNC-only.

**LinuxCNC RS274**: laser is spindle `$1` (`SPINDLE_SELECT`); header is `G21/G90/G94/T<n> M6/G43
H<n>` (`cmd_tool_comp()` — a *function*, not a constant, so it follows the `LASER_TOOL` preference,
default 100, set per laser profile) then `M5 $1`; arm once with `CMD_ARM` (`M3` at zero power +
dwell), power per segment via `S…` (`CMD_BEAM_ON/OFF`), disarm `M5`, end `M2`. Power fields are
scaled 0..`S_MAX` (preference `s_max`, default 1000 — panels use `setRange(0, core.S_MAX)`, **never**
a hard-coded 1000). The emitted `T<n> M6` loads the laser tool itself (no-op if already loaded) and
`G43 H<n>` applies its X/Y offsets (tool.tbl) + probed Z.

> Note on `tool.tbl`: the Z offset in it is a **measurement, not a setting** —
> `subroutines/toolchange.ngc` rewrites it (`G10 L1 P<tool> Z<offset>`) at **every** `M6`. Only X
> and Y survive. Don't advise editing that Z.

## Mandatory sanitizer

`sanitize_gcode_for_linuxcnc(text)` at every generator's return. LinuxCNC rejects **nested
parentheses** in comments (`passe(s)`, `(par bande de Z)`) and **non-ASCII bytes** (French accents);
the sanitizer brackets inner parens and transliterates. It is **idempotent**, so it's safe for
combined jobs that re-wrap sub-bodies.

## Standard parameters

- **`body_only=True`** omits header/arming/footer so a body can be embedded in a combined job with a
  single arm/disarm (see `generate_gcode_combined`).
- **`frame_only=True`** emits only the bounding rectangle (a separate framing-check file).
- **`min_safe_z`** imposes a common retract floor so stacked operations don't plunge at the wrong
  height (`_operation_intrinsic_safe_z`). Its `"curved"`/`"curved_cut"` branch must mirror
  `generate_gcode_curved`'s OWN safe-Z formula **term for term** — it forgot `wave_amplitude` until
  v1.81.1 (while the `"filled"` branch right below it had it), so a Marquage "vague" operation could
  impose too low a floor on the *other* operations sharing the job.
- **`TRAVEL_CLEARANCE_MM`** is the flyover margin over the work Z for transits. On flat work it
  should be small or 0 — lifting per hatch line is the classic wasteful bug; transit at the working
  Z, laser off.

## Path blending — `PATH_BLEND_TOLERANCE_MM = 0.05` (v1.86.0)

`cmd_path_blend()` emits `G64 P0.050` in every laser preamble (None in GRBL/grblHAL). Two traps,
both counter-intuitive:

1. A **bare `G64` does not mean "no blending"** — it means "blend at max speed with NO tolerance
   bound". Adding `P` therefore **constrains** the machine, it doesn't loosen it.
2. A job emitting **no `G64` at all inherits the machine's `RS274NGC_STARTUP_CODE`**. On the user's
   PrintNC that is `G64 P0.001` — a 1 µm corner tolerance, forcing a near-full stop at every
   direction change, tens of thousands of times in a hatched engraving. **Emitting nothing is not a
   neutral choice.**

0.05 mm is far below the finest measured burn width (0.10 mm) and 50× below the widest (2.60 mm), so
it cannot show on the work. **`generate_gcode_offset_test` is deliberately excluded**: it engraves a
cross whose corner geometry IS the measurement, so it keeps the machine's tight tolerance. Any new
generator must make that call consciously — blending is right for burning, wrong for measuring
geometry.

## Micro-strokes and their DIRECTION — `micro_trait_oriente(dots, i, half)`

Each dot is a micro-line (never a `G4` dwell, see CLAUDE.md), **and it must be drawn in the
direction its row is being traversed**. `halftone_dots` / `zdots_marks` already serpentine the point
order, but drawing every micro-line left→right means that on a right-to-left row the head positions
at `x-half`, burns rightward, then backs up past the next dot — one back-and-forth per dot, over
tens of thousands of dots.

The direction is read from the neighbour **on the same row** (compare `y`), never blindly from the
previous entry.

**This bug shipped twice.** v1.93.0 fixed `generate_gcode_halftone` and
`generate_gcode_photo_sampler` (measured on 2400 dots: 955 → 787 mm of beam-off travel, −18 %,
micro-lines at identical positions — only their direction changed). `generate_gcode_photo_zdots` was
**missed and kept the defect for a month**; on a 134 × 201 portrait that was **26 600 direction
reversals and 5.3 m** of useless travel (−26 % once fixed). Nothing could flag it: valid G-code,
correct image, only the *noise* betrayed it.

> **Rule this earns:** when you fix a generator, `grep` the faulty pattern across **all** generators
> of that family in the same commit, and write the test as a **property over the whole family** —
> `tests/test_micro_traits.py` counts direction reversals inside a single row
> (`harness.demi_tours_x`) for all 7 tramages, expecting zero.

## Two more emission traps

- **Sampler band labels engrave at `Z_WORK_MM`, not `z_work`**: in that mire `z_work` is the
  DEFOCUSED band height, so the digits came out fat and blurry. Following bands re-establish their
  own Z, so no explicit return is needed. (`generate_gcode_test_grid` already had this right; it was
  `generate_gcode_photo_sampler` that lacked the separation.)
- **Defocus goes on `cell_z_offset`, NEVER on `z_work`.** `generate_gcode_test_grid` engraves axis
  labels at `z_work` and the border at `z_border` precisely so they stay sharp while only the cells
  are defocused; raising `z_work` blurs all three. `_on_recipe_selected` also resets `z_work` to
  `core.Z_WORK_MM` unconditionally — the panel restores last field values across sessions, so a
  defocused height left behind silently poisons every later job (observed).

## Chain ordering (v1.82.0)

`generate_gcode_curved` runs `order_chains_by_proximity(chains)` right after `chain_edges`, so every
mode built on it (Marquage AND the fill/contour bodies of Gravure remplie) visits disjoint chains
nearest-first, reversing a chain when that end is closer. `generate_hatch_edges`' line-by-line zigzag
only orders WITHIN a hatch line; as soon as a line is cut into a different number of segments than
its neighbour (any shape with holes — orbits, cavities, letter counters), the "next line" jumps
across the whole piece.

Measured on the user's real skull (9268 chains): **56 m → 5.1 m** of travel (−91 %), engraved length
identical to the millimetre, G-code 190k → 171k lines with the SAME 133 293 G1 moves.

Nearest-neighbour search goes through a grid indexed like `generate_hatch_edges`' bands, scanned in
expanding rings and stopped once the best candidate beats the next ring's edge — same criterion as
exhaustive search, **25 s → 0.16 s**. Size the cell on the bounding box's largest **EXTENT**, never
its area: collinear chains (a single hatch line, one line of text) give zero area, hence a
microscopic cell and a hang. Exact ties are common on regular hatching and grid vs. exhaustive break
them differently (~1 % of the total), so only tie-free point sets can be compared
millimetre-for-millimetre between the two.

## Stepped-ramp generators

`generate_gcode_power_ramp_lines` and the defocus calibration band draw tick/graduation marks that
must land on the trajectory the G-code **actually** follows, not a naive continuous interpolation.
The moved axis (X) and the ramped value (Z or S) are often parametrized differently across the same
`n_steps`/`k` loop (e.g. `x1 = length*(k+1)/n_steps` vs `t = k/(n_steps-1)`), so a plain
`x = length*(target-start)/(end-start)` silently lands a tick one step early or late.

Reconstruct the `(x, value)` breakpoints exactly like the generation loop and interpolate within
those — **and check the result against an actually-generated `.ngc` file.** A headless test that only
re-derives the same formula will pass while still being wrong. Fixed in v1.71.5 after the user caught
it on a real file, for the Z tick only; the POWER tick kept the naive formula until v1.81.1, because
power is a **step** function, not a ramp (S is set once per G1 block and held for the whole segment),
so its fix finds the first real breakpoint whose power reaches the target instead of interpolating.

## Defocus model and MEASURED burn width

A linear divergence cone calibrated from **two real measurements** (never guessed):
`defocus_divergence_half_angle(d_focus, d_calib, z_calib)` → `spot_diameter_at_defocus(z, …)` →
`defocus_for_fill_spacing(spacing, …)`.

The **fill is inset by the spot radius** so the burn stays inside the outline (`fill_inset` in
`build_test_grid_cells` / `build_filled_engraving_edges`, via square inset or
`Part.Face.makeOffset2D(-r)`). `inset_face_robuste` re-polygonizes wires first — OCC segfaults on
some imported BSplines — and rebuilds the polygonal face DIRECTLY from the known structure
(`face.OuterWire` CCW + holes CW by signed area, XY plane only; other planes keep the Bullseye
build), because `FaceMakerBullseye`'s O(n²) nesting sort costs ~11 s for nothing on a ~180-wire face
whose structure is already known. On offset failure it discriminates by `Area > 2·perimeter·inset`: a
genuinely thin stroke is skipped as before (the contour blackens it), but a LARGE face OCC chokes on
falls back to filling WITHOUT inset plus a console warning, instead of silently producing an empty
fill.

When a contour is drawn, `TaskPanelFilledEngraving._fill_inset` reduces that inset by the
**contour's burn radius** so the fill tucks *under* the contour (re-burned at focus on top) —
closing the pale liseré at the edge, most visible at high defocus where the optical spot
over-estimates the real burn width.

The **measured** burn width — which drives fill spacing/inset, *not* the optical spot — is
`burn_width_defocus_scaled(power, feed, defocus)`, **feed-aware** since v1.31.0. Calibration is
burned via three planks (`generate_gcode_planche_focus` / `_defocus` / `_spot`, all translated to
piece zero on write): Planche 2 burns an S×F grid at **each** `DEFOCUS_LEVELS_MM` level (15 and
36 mm), and the function interpolates **bilinearly in (S, F)** at each level (shared
`_bilinear_burn`, same as `burn_width_at` at focus: S linear, F log) then linearly between the two
bracketing levels.

**Below** the lowest measured level it interpolates between the directly-measured **focus** table and
that level (v1.80.0) — the fill's own defocus is only a couple tenths of a mm (0.10 mm for a 0.26 mm
spacing), and down there the burn is governed by heating time, not optics. Extrapolating the optical
cone to z≈0 over-estimated it **2.1×** on beech (0.21 mm announced for 0.10 mm measured), so hatches
the workbench believed solid came out striped. Only *above* the highest level (or with no focus
table) does it fall back to the proportional-to-optical-spot extrapolation.

Measurements are entered inline in the Test-grid panel's "② Entrer les mesures" (`_GrilleResultats`
per plank/level, lock-by-default; stored with each point's `z_offset`, snapped to the nearest
standard level by `_snap_defocus_level` on read — legacy 15.34 → 15; legacy single-feed data lands in
the F800 column).

### Always pass `material` to the burn-width functions

`_burn_width_material(None)` only guesses when *exactly one* material has been measured; with two or
more it returns `None`, and every caller silently degrades — `burn_width_defocus_scaled` returns
`None`, `_build_edges` skips the correction entirely, and the hatch keeps the requested spacing
however narrow the real trace is. That is how a beech fill at S200/F1800 (0.10 mm burned, 0.26 mm
spacing → **62 % bare wood**) shipped as G-code the workbench believed solid.
`TaskPanelFilledEngraving._materiau()` (v1.80.0) feeds the "Nuancier matériau" combo into all five of
its calls; other panels still rely on the single-material guess.

### Covering-setting search, and its inverse

`reglage_couvrant_le_pas` (spacing → covering setting) is **defocus-aware** (v1.80.1): the spacing
itself sets the defocus (0.90 mm spacing → 13 mm of lift), and a trace measuring 0.30 mm at focus
measures 1.0 mm up there, so candidates are the (S, F) couples measured at the level *nearest the
working defocus*, scored with the same interpolator as the verdict — so suggestion and verdict can
never contradict each other.

`espacement_pour_reglage(power, feed, material, borne_haute)` (v1.81.0) is the inverse: setting →
largest covering spacing, so choosing a tone is one decision instead of two. It **cannot** be a
closed-form inversion of `defocus_for_fill_spacing`: using the tone's own measured width directly, or
inverting the optical cone to reproduce the tone's z_offset, both degenerate to the SAME answer and
undercover **29 of 41** real measured tones by up to 0.11 mm — found by sweeping actual nuancier
data, not by reasoning about the formulas. It bisects for the root of
`f(pas) = burn_width_defocus_scaled(power, feed, defocus_for_fill_spacing(pas), material) - pas`,
bounded above by `borne_haute` (the tone's own width when the caller has one, else 3× the
focus-width). Verified zero undercoverage across all 41 tones, ~0.1 ms/call. An explicit
`borne_haute` is honored exactly as given, however tight; the fallback-only safeguard must never leak
onto a caller-supplied bound (a real bug its own test suite caught before shipping).

## Vector fonts

**7-segment label font** — `text_to_edges` / `_char_to_edges` / `_FONT_GLYPHS`: digits `0-9`, `S`,
`F`, `.` and `-`, so labels ("S400", "8.25") need no external font file. Extend `_FONT_GLYPHS` (or
the `.` special case) for a new glyph.

**Single-line (monoline) fonts** — genuinely single-stroke vector fonts for engraving text as "stick"
letters (one stroke per branch, like a pen plotter), the right tool when the medial axis can't help
(holed letters). Registry `HERSHEY_FONTS` maps a key → display label, each a sibling data module
`hershey_font[_clé].py` (`GLYPHES[char] = (adv, [strokes])` in font units, baseline y=0,
`CAP_HEIGHT` ≈ 662), generated from a public-domain **Hershey** SVG font — keep the credit in each
module's docstring. `hershey_font.py` (no suffix) is the historic default "sans";
`hershey_font_script.py` adds cursive "script".

Only genuinely single-stroke Hershey variants belong here — most "Med"/"Bold"/"Serif" variants draw
each stroke **twice** (duplex/outline) and defeat the point of the mode; check a reference glyph's
path for a low, non-doubled stroke count before adding one. `_hershey_module(font)` resolves a key
(silent fallback to "sans"). Core: `single_line_text_to_edges(text, height, char_spacing,
line_spacing, font="sans")` (height = cap height) and `create_single_line_text_object(...)`; the
**Texte (trait simple)** mode creates a `Part::Feature` wire to engrave with **Marquage**.

To add a font, generate a new sibling module from the source SVG font (same structure — don't
hand-edit) and register it. To add glyphs, regenerate the module. **Known pre-existing gap** in the
shipped `hershey_font.py`: a handful of glyphs (ç, Ç, ß, £, ı, İ, æ, Æ…) exist in `GLYPHES` with an
**empty** stroke list — the original generator dropped curve-only glyphs instead of keeping their
parseable subpaths — so they render as invisible blanks. Not yet fixed.

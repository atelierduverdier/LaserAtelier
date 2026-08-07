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

## Crossing a WHITE run — `TRANSIT_BLANC_MINI_MM` (v2.45.0), frozen 2026-08-06

A beam-off move at the *engraving* feed is the single most expensive defect a raster can carry, and
it is invisible: valid G-code, correct image. Christophe's LightBurn export for his Falcon 2 shows
what it costs — two parts 101 mm apart, filled in one sweep, **4 359 beam-off moves of a 128 mm
median = 55.9 % of the path**, close to 4 hours out of 7.

**The workbench does not have it**, and that is measured over the 70 really-engraved `.ngc` files:
**1.51 %** of the path, against LightBurn's 55.9 %. `TRANSIT_BLANC_MINI_MM = 5.0` makes any white
run of at least that length traverse at `RAPID_FEED_MM_MIN` — as a `G1` at rapid feed, **not a
`G0`**: motion stays continuous and the queue is never drained, which also keeps the M67 channel
happy. Four call sites, and the mechanism was extended twice after its introduction (the spiral in
v2.52.0, the spindle in v2.56.0 — where it must fire *only where the Z is flat*).

Extended twice and never tested: that is the exact shape of the micro-stroke defect, which shipped
**twice** because the first generator's fix was never turned into a property over the family.
`tests/test_transit_blanc.py` closes it — an image with a deliberate 60 mm void, zero slow crossings
across the raster family, and §1 refuses to run at all if the fixture can no longer see the defect
(raising the threshold makes §1 fail rather than §2 pass).

Two real files still carry slow crossings — `gravure_photo4.ngc` (4.6 m) and
`mire_tramages_photo.ngc` (33 mm) — stamped **v1.96.4** and **v1.91.0**, both *before* v2.45.0. That
is history, not a live defect, so §4 prints rather than asserts: the same rule as for measurements
that move when Christophe re-measures.

## Air assist — `assistance_air` (v2.99.37, M7/M8 in v2.99.39)

Bench engravers drive their air pump with `M8`/`M9`. `ASSISTANCE_AIR` (per-laser) grafts them onto
**`CMD_ARM` / `CMD_DISARM` in `_apply_settings_config`, last, after the dialect rewrites them** —
those two templates are what the ten generator families emit (35 and 50 call sites), and `body_only`
strips them from a combined job's bodies, so the wrapper arms once. An `M8` written into each
generator would have re-lit an already-running pump once per operation.

**M7 or M8 — the WIRING decides, and shipping M8 hardcoded was a defect.** RS274 separates `M7`
(mist) from `M8` (flood): two outputs, two HAL pins, and **the one that isn't wired does nothing at
all**. Christophe mounted his pump on M7 on the PrintNC the day after v2.99.37 shipped; LightBurn's
Falcon2 export uses M8. Hardcoding M8 would have produced a perfectly valid file that engraves
**without air**, and nothing in it would have said so — the quietest kind of defect. So the setting
is a choice (`""` / `"M7"` / `"M8"`), per-laser, which is exactly right since a profile *is* a
machine. `M9` is unchanged: it closes both, whichever opened.

`_cast_air` **accepts a bool** so configs written by v2.99.37 migrate (`true` → `"M8"`). Without it
`_apply_settings_config` would have seen an invalid value, warned to the console, kept the default —
and cut the air, with nobody connecting cause to effect.

**The order comes from a file that actually ran**, not from reasoning: Christophe's LightBurn 1.3.01
export for his Falcon 2 puts `M8` right after `M4` and `M9` **before** the final `M5`. Reproduced
verbatim.

**The property is NOT "exactly one pair".** That was an assumption, and `generate_gcode_planche_defocus`
disproved it: it burns the framing rectangle, disarms, stops on `M0` for the operator to check the
placement, then re-arms —
`M4 → M8 → [frame] → M5 → M0 → M4 → M8 → [board] → M9 → M5`. Two `M8`, both correct: `M8` on a
running pump does nothing. What must be unique is the **cut-off** — a stray `M9` and the tail of the
job engraves without air, silently. `tests/test_assistance_air.py` §2 asserts `M8 ≥ 1` and `M9 == 1`.

Second weak anchor fixed in the same pass: "last engraved move" looked for an `S` word, but a marking
sets its power **once** and then emits bare `G1`s — the anchor landed on line 16 of a 557-line file
and the check passed without checking. Use the last `G1`.

**It changes what burns.** Air gives a brown halo around the trace, none without it, and the lens
fouls faster dry — the hidden variable no measurement board records (see the mire note above). So it
is per-laser, and the tooltip says switching it invalidates the regime the burn widths were measured
in.

## Machines with NO Z axis — `machine_sans_axe_z` (v2.99.36)

Bench diode engravers (Creality Falcon, Ortur, xTool) focus by hand and have **no Z motor**.
`MACHINE_SANS_AXE_Z` (per-laser, like the dialect) makes `retirer_axe_z` strip every `Z` word and
delete the moves that carried nothing else.

It is not optional on such a machine: **every file this workbench produces carries Z words**.
Measured — a flat marking with work-Z 0 *and* clearance 0 still emits `G0 Z5.0000`, the start/end
safety height (`z_safe_start_end = … + 5.0`, hardcoded). The controller accepts the word, believes
it is moving an absent axis, spends time on it, and raises a soft-limit alarm when `$20=1`
(Z travel = 0).

**Stripping happens in `sanitize_gcode_for_linuxcnc`**, the one path all ten generator families
return through, and it stays idempotent — a combined job re-sanitises already-sanitised bodies.
Two independent guards hold that idempotence (the early return when nothing was removed, and the
"note already present" check); **sabotaging either one alone leaves the property standing**, which
is noted in the test so nobody later concludes the check is decorative.

**It announces itself when the Z carried information.** Removing a flyover height changes nothing
about what burns; removing a Z that *varied during a `G1`* removes defocus, the spindle or relief
following — the job no longer engraves what was computed. `retirer_axe_z` counts those moves,
writes the count into the file header and warns on the console (192 on a `vague`-style marking).
A flat marking gets the plain note and no alarm — an alert that cries wolf stops being read.

Trap paid on the way, and it is the one this file already documents: the first version appended
the alert **after** the closing parenthesis (`(…) -- ATTENTION : 192 …`), so the interpreter would
have read it as CODE. A comment stays on its own line and nothing follows it. `tests/test_sans_axe_z.py`
§3 freezes both that and the absence of orphan `G0` lines.

## Mandatory sanitizer

**An UNCLOSED comment kills the file at LOAD time** (v2.13.3). A `(` with no `)` after it makes
LinuxCNC refuse the program outright — "Unclosed comment found", the job never starts. The sanitizer
used to pass such a line through untouched (`if end <= start: out.append(line)`), which is the one
failure mode it exists to prevent. It now closes the comment at end of line; RS274 has no multi-line
comment, so that is always the correct repair, and it stays idempotent. Found on 2026-07-31 when a
hand-built measurement board split a header sentence across two lines. **When building comment text
by hand, keep each comment on its own line** and assert `line.count("(") == line.count(")")` before
writing — don't lean on the sanitizer to paper over malformed text.

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

## Three gradients, and they are NOT the same thing (v2.9.0, v2.12.0)

`"degrade"` (v1.x) ramps the defocus by **spatial projection**: `t = (p·u - pmin) / span`, `u` given
by `deg_angle`, normalised over the bounding extent of *all* chains. `"degrade_trace"` (v2.9.0) ramps
by **curvilinear abscissa along each chain**. On a straight line oriented along `deg_angle` the two
coincide; on a spiral, a circle, or anything doubling back, the first follows POSITION and the second
follows the PATH. Keep both — the user asked for the second precisely because the first could not
taper a spiral from outside to centre.

`rampe_trace_dz(chain, dz0, dz1, aller_retour)` returns one dz per point. Design points, all
user decisions from 2026-07-31:

- **Each chain carries the WHOLE ramp.** Two selected lines give two identical tapers, so the result
  can't depend on the visiting order — which `order_chains_by_proximity` picks for travel, not for
  drawing. Test: a 100 mm and a 60 mm line must show the same Z stroke.
- **Closed loops are a user choice, not a hidden rule.** A plain ramp brings `dz1` back beside `dz0`,
  so the closure shows as a step; `aller_retour` reaches `dz1` at MID-path and closes on the starting
  width. Ignored on an open chain — it would contradict "width at the end". `chaine_fermee` tests XY
  only: a contour projected on relief has different Z at its two ends.
- **The approach `G0` must already carry `dzs[0]`**, exactly like `"degrade"` — otherwise the first
  `G1` jumps the full ramp height (64.8 mm on the workshop's 4 mm setting) over one
  `DISCRETIZE_DISTANCE` of XY. Measured after the fix: 0.19 mm instead of 64.8.
- **dz is never negative**, in either ramp direction. That matters beyond aesthetics: the nozzle
  collision check runs on the point's *native* Z, so it is only conservative as long as the style
  merely lifts the head. `_operation_intrinsic_safe_z` and the generator's own `z_safe_start_end`
  both ignore the gradient lift, and are therefore consistent with each other — don't "fix" one
  alone.

### `"degrade_puissance"` — the one that actually darkens (v2.12.0)

**Both width gradients keep `S` CONSTANT and only raise Z.** That is the fact everyone gets wrong,
including me: on 2026-07-31 I renamed `degrade_trace` "dégradé de tonalité" because the user called
it that, and only measuring the emitted G-code showed the truth — S800 throughout, Z +0 → +47.2 mm
for a 0.3 → 3.0 mm taper, i.e. fluence 8.00 → 0.71. A trace ten times wider gets **eleven times less
energy per mm²**: it is not darker, it is wider and usually *paler*. It reads as a tone gradient on
**hatching** (wider strokes cover more), never on a lone line — which is exactly the case the user
tried, and reported as not matching the name.

`"degrade_puissance"` is the inverse and the literal answer to "clair au début, foncé à la fin":
**Z constant, `S` ramped along the curvilinear abscissa**, `deg_s_debut` → `deg_s_fin`, clamped to
`[0, S_MAX]`.

**It does NOT hold the trace width constant, and v2.12.0 shipped claiming it did** — G-code header,
tooltip, manual and the preview all said "largeur inchangée". What is constant is the nozzle height
and hence the *optical* spot; the **burned** width still follows power, because at low power only the
beam's core crosses the wood's burn threshold. Measured on beech at focus, F800: **0.10 mm at S200
against 0.30 at S1000, i.e. 3×**. The project already knew this (it is why
`width_for_darkness` exists) — it just wasn't applied when the style was written. It stays clearly
distinct from a width gradient: 3× against 11× for a 0.3 → 3.0 mm fuseau on the same selection, which
is what `test_fuseau.py` §15 now asserts instead of the old "constant width" claim that froze the
defect. It reuses `rampe_trace_dz` unchanged — the ramp interpolates *a value* along the path
and does not care whether that value is a height or a power — so it inherits the whole-ramp-per-chain
guarantee and the `aller_retour` closed-loop option for free. Emission mirrors the `vague` branch
(per-point `cmd_power_prefix` / `cmd_power_suffix`), so it obeys the M67 dialect: **with M67 the
per-point power changes are free; without it, every `S` between two `G1` stops the machine** (proved
on the PrintNC by two twin files — see the M67 note above). The panel greys out the global power
field on this style, since a ramped power makes it meaningless.

### A width ramp at constant power is a FLUENCE ramp — `deg_s_rampe` (v2.13.0)

The spiral engraved on 2026-07-31 (0.3 → 4.0 mm, S1000 throughout) came off **mottled grey at the
wide end and gouged/carbonised at the thin end**. That is not a bug, it is what constant power over a
13× width ratio *means*: fluence goes as 1/width. The manual said so; the wood made it undeniable.

`deg_s_rampe` (default **off**, so old files stay reproducible bit for bit) superposes a power ramp
on **both** width gradients — `deg_s_debut` → `deg_s_fin`, on the same parametrisation as the width
(curvilinear for `degrade_trace`, spatial projection for `degrade`, via the same
`rampe_trace_dz` / `rampe_direction_dz`). The emission branches gain an S-carrying variant; the
old loop is kept verbatim for the unchecked case.

`puissance_fluence_largeur(power_ref, w_ref, w_cible)` is the **single** model — S proportional to
spot diameter — and `wave_fluence_powers` now delegates to it rather than carrying a second copy.

**The honest limit, and it must stay in the UI**: on that 0.3 → 4.0 mm taper, constant tone needs
**S75** at the thin end, below the lowest *measured* power (S200 on beech at F800) where the width
table says nothing at all. Anchoring at the other end needs **S12000**. So a uniform tone over 13×
does not exist on this machine — the panel computes the number, then says which wall it hits. Do not
"fix" this by silently clamping: a clamped suggestion is a made-up recipe.

**Defect this uncovered, worth remembering**: `_update_style_ui` greyed `spn_power` for the ramped
styles, then an unconditional `setEnabled(True)` a few lines below re-enabled it. Two mechanisms on
one widget, last writer wins — the v2.12.0 power gradient shipped with its power field still live and
nothing tested it. Any new `setEnabled` on a shared widget must be checked against the whole function,
not just its own branch.

### The preview must show the taper, not its average (v2.9.1)

`TaskPanelCurved`'s photo preview computed **one** width for the whole drawing, per style: the
directional gradient painted the *mean* of the two widths, and `degrade_trace` fell through to the
`plein` branch — the focus width. A 0.3 → 3 mm taper rendered as a uniform thin line, reported the
day it shipped. A preview that doesn't show what you'll get is worse than none.

`_strokes_degrade` now chains the edges like the generator does (the along-path ramp runs over a
CHAIN, not a lone edge) and emits one stroke per segment, its width from
`burn_width_defocus_scaled` at that point's dz. Both dz sources are the generator's own
(`rampe_direction_dz`, extracted from an inline closure for exactly this reason, and
`rampe_trace_dz`), so preview and G-code cannot disagree — §10 of `test_fuseau.py` asserts both are
called.

## The engraved measuring mire (v2.14.0)

`mire_de_mesure(x_min, y_min, x_max, y_max, …)` → `(bande, label_edges, infos)` in the neutral
`_emit_flat_marks` form, plus `_bbox_planche` / `_ajouter_mire` / `_entete_mire`. Wired into
**Planche 1 (focus)** and **Planche 2 (defocus)** behind `mire=True`; `mire=False` reproduces the old
G-code exactly. `MIRE_POWER` / `MIRE_FEED` are per-laser settings (`mire_power`, `mire_feed`).

Four design points, each earned:

- **Engraved, not laid on.** A steel rule sitting on the board is 0.5–1 mm *above* the surface, so a
  macro sees it at a different angle from the trace being measured — parallax. An engraved scale
  shares the plane *and* the machine coordinate frame.
- **Four fiducials, not one.** Four correspondences let software correct **perspective** (homography),
  not just scale; a hand-held macro is never perpendicular and that is the dominant error. The
  enclosing rectangle is rounded to whole 10 mm so its dimensions are exact and can be announced in
  the header — the rectangle is the reference, the ruler is for the eye and for tight framings where
  the crosses fall outside the field.
- **Slow on purpose.** The ruler is dozens of short strokes separated by rapids, hence dozens of
  accelerations; at F1200 the workshop's PLA camera mount vibrated and the crosses came out **wavy**,
  which destroys exactly what a fiducial is for. For a fiducial, *straight beats thin* — a slightly
  fat clean line gives a better centre than a thin wobbly one.
- **It refuses rather than overlaps.** `mire_de_mesure` returns `(None, None, None)` when the
  clearance under the content would go negative. The first hand-built version engraved the widest
  trace straight through the ruler digits — unmeasurable, and visible only in the preview.

**What it found on day one**: a trace the width table called 0.30 mm measured **0.50** on a photo,
then 0.50 again with Christophe's calliper. The focus burn-width table described a machine state that
no longer existed. Hidden variable surfaced at the same time and **recorded nowhere**: air assist
on/off changes the browning around the trace (he sees a brown halo with air, clean without).

## F applies to the VECTOR — that is a burn defect, not just a slow job

`avance_compensee(dxy, dz, feed)` raises the commanded feed by `d3D/dXY` on every engraving block
whose Z moves, capped so the Z axis stays under `Z_MAX_FEED_MM_MIN`.

In G94, `F` is the feed along the **programmed path**. Where the spindle climbs at its slope limit —
7.5 mm of Z per mm of trace, i.e. exactly at the start and end of every calligraphy gesture — the
head advances in XY **7.57× slower** than announced (`sqrt(1 + 7.5²)`), at constant beam. The wood
receives the energy of 7.57 mm of travel spread over 1 mm of visible trace.

**The project already knew that ratio and used it for the wrong question.** Since v2.54.0 it explains
job DURATION (2.1× on a spindle portrait); nobody connected it to burning. Christophe, 04/08/2026,
photo of an engraved "Atelier du Verdier" with seventeen blobs circled: *"je pense qu'il y a trop de
puissance ou on ne va pas assez vite dans certains endroits"*. Both, and one cause.

Measured on the file he ran — energy per mm of **visible trace**, `S·d3D/(F·dXY)`:

| | before | after |
|---|---|---|
| segments above 2× the median | 20.6 % | 0.2 % |
| segments above 5× the median | 7.5 % | 0 % |
| worst | 12.4× | 2.1× |
| job time | 4.6 min | 2.3 min |

Compensating also puts the machine back into the regime the **burn-width table was measured in** —
it is not a taste setting.

**The same defect lives in other generators**, measured over the workshop's own `.ngc` files
(fraction of engraving segments at `d3D/dXY ≥ 1.5`): `gravure_photo` 13–15 %, `catalogue` 4.8 %,
`marquage2` (dégradé) 4.9 %, `spirale_trait_degressif` 2.0 %. Only Calligraphie is wired so far,
deliberately: correcting the others changes engravings whose power and coverage Christophe tuned by
eye on wood, so that call is his.

## Chain ordering (v1.82.0)

**`sens_libre=False` (v2.67.0) forbids the reversal.** Ordering picks, for each chain, whichever
direction shortens the jump — harmless for every mode where a stroke has no intrinsic direction, and
destructive for calligraphy, where the direction of the stroke *is* the gesture. Whatever
`calligraphie.py` computed upstream was therefore never what got engraved. `sens_de_la_main` orients
each gesture first (down if it is mostly vertical — a pen presses on the downstroke; right otherwise
— you write left to right), then the ordering runs with reversal disabled. On "Atelier du Verdier":
9 gestures out of 20 descended, now 20 out of 20, for 122 → 203 mm of empty travel — under one second
at G0 on a 2.3-minute job.

Verify this **on the emitted G-code**, never on the function: the whole defect lived *between* the
two, in the ordering. And give the fixture more than one gesture — the single tapered stroke of §4
reports "1 out of 1" and proves nothing.

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

### The level is free, but a level must be measured as a level (v2.4.0)

`SNAP_DEFOCUS_TOLERANCE_MM` was **5 mm**, sized when only two levels existed: a deliberately burned
defocus 40 was read back as 36 and poured into a grid it did not belong to (that happened — the
ramp's S716/F600 at 40 mm). Now **2 mm** — enough for measurement noise, never enough to merge two
ramp graduations (5 mm apart). `niveaux_defocus_mesures(material)` reports what actually exists.

`_niveaux_exploitables` then keeps, as interpolation anchors, only levels holding **at least two
distinct powers**. A one-power level makes `_bilinear_burn` return the same width for every power and
therefore **flattens the whole span it bounds**: the four lone ramp points dropped the predicted
S1000/F200 width from 2.26 to 1.50 mm at defocus 30 and from 3.80 to 3.00 at defocus 55, and two
hatch pitches (1.50 and 1.70 mm) lost every covering setting. Those same points *confirmed* the
model — at the exact measured point it predicted 1.61/2.08/3.29/4.10 for 1.50/2.00/3.00/4.00, i.e.
+2 to +10 % — so they are not wrong, they are **incomplete**. Measuring a second power at the same
defocus promotes the level to a full anchor. Fallback: if no level qualifies, keep them all.

### Always pass `material` to the burn-width functions

`_burn_width_material(None)` only guesses when *exactly one* material has been measured; with two or
more it returns `None`, and every caller silently degrades — `burn_width_defocus_scaled` returns
`None`, `_build_edges` skips the correction entirely, and the hatch keeps the requested spacing
however narrow the real trace is. That is how a beech fill at S200/F1800 (0.10 mm burned, 0.26 mm
spacing → **62 % bare wood**) shipped as G-code the workbench believed solid.
`TaskPanelFilledEngraving._materiau()` (v1.80.0) feeds the "Nuancier matériau" combo into all five of
its calls.

**`TaskPanelCurved`'s photo preview had the same hole until v2.13.2** — three calls with no material,
so on this workshop (beech *and* MDF measured) they returned None on every single call and the
preview silently painted the **optical spot** instead of the measured burn. Its own docstring said
"largeur BRÛLÉE mesurée si on l'a, sinon le point optique"; "si on l'a" was never true. Visible cost:
2.80 mm painted as 3.00 at the wide end of a fuseau, and 0.30 instead of 0.10 at focus — a 3× error
on the thin end, which also poisons `_tone_burn(power, feed, width)` fed from it. `test_fuseau.py` §9
now asserts the painted width **differs from the optical spot**, so an omitted material fails the
test instead of looking plausible.

**Closed in v2.32.0**: `_strokes_from_operation` (the combined-job preview) had the same three
calls and had stayed broken because a combined operation's `params` are *the exact kwargs its
generator takes*, so slipping a `"material"` key in would break the `**params` call. The material
now travels as a **sibling of `params`** (`op["materiau"]`), set by the `filled` and `curved`
builders from the panel's own shade picker. On this workshop (beech *and* MDF measured) the three
calls returned None every time, so the combined preview painted the **optical spot** — 1.16 mm where
the measured burn is 1.43 at S1000/F200/defocus 15.

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

### Coverage is only half the question — `remplissage_noir_le_plus_econome` (v2.3.0)

A fill can be perfectly **solid and completely overcooked**; the two failures are opposite and
checking one says nothing about the other. Proved on wood: a beech square at S1000/F800 at focus,
pitch 0.26, burn 0.30 mm → the panel's coverage verdict read green "Remplissage plein", exactly
right, and the square came off **carbonized**. Nothing else in the panel said a word.

`energie_surfacique(power, feed, spacing)` = `S/(pitch·v)` — an **index, not joules** (S has no
physical unit); only ratios between two settings of the same laser mean anything. It's the same
quantity the calibrated tramages call areal fluence: what the wood receives is governed by how far
you ADVANCE between passes, not by the trace width.

`remplissage_noir_le_plus_econome(material)` returns the cheapest measured tone judged ≥ 95 % black.
**Both sides must be computed the same way** — the pitch for each candidate comes from
`espacement_pour_reglage`, i.e. exactly the fill you get by clicking that tone. This is not
fastidiousness: a tone's stored `width` is sometimes a calliper-measured burn width and sometimes the
PITCH of a raster calibration band, and dividing by one then by the other compares two different
quantities. On the workshop's beech data the naive reading makes `S1000/F2000` look like 0.625 when
its real fill costs 5.000 — **8× off, and it would have stolen the reference slot** (asserted in
`tests/test_energie_remplissage.py`).

`SEUIL_ENERGIE_REMPLISSAGE = 2.0` gates the panel's warning. It is a **waste** threshold, never a
carbonization threshold — at equal power the energy ratio and the duration ratio are the same number
(both go as `1/(pitch·F)`). The data does not support predicting damage: on MDF, tones judged 97 %
sit at 4× the cheapest without complaint, while on beech 2.8× charred. **The damage threshold is
material-dependent; this ratio is not it.**

## Vector fonts

**7-segment label font** — `text_to_edges` / `_char_to_edges` / `_FONT_GLYPHS`: digits `0-9`, `S`,
`F`, `.` and `-`, so labels ("S400", "8.25") need no external font file. Extend `_FONT_GLYPHS` (or
the `.` special case) for a new glyph.

**Single-line (monoline) fonts** — genuinely single-stroke vector fonts for engraving text as "stick"
letters (one stroke per branch, like a pen plotter). Registry `HERSHEY_FONTS` maps a key → display
label, each a data module `polices_monotrait/hershey_font[_clé].py` (`GLYPHES[char] = (adv, [strokes])` in font
units, baseline y=0, `CAP_HEIGHT`). **45 since v2.77.0**: 44 from oskay/svg-fonts (EMS in SIL OFL,
Hershey in the public domain) and Relief SingleLine (SIL OFL, designed for CNC), plus
**Verdier** — drawn stroke by stroke by `outils/creer_police_verdier.py`, so converted from
nothing, under no third-party licence, carrying the workshop's bowler hat on `¤` and the
œ/Œ that only Relief had. `_hershey_module`
imports **lazily**, so 2.6 MB on disk costs nothing until one is picked — don't "preload for speed".

**`outils/generer_police_monotrait.py` produces them**, and it did not exist before v2.60.0 although
both shipped modules said "ne pas éditer à la main". A datum you can no longer produce is a datum
nobody dares correct — which is exactly why the gap below lasted months. It reuses `svg_import`'s
path tokeniser rather than growing a second one.

Three traps it now handles, each found by measuring:

- **CAP_HEIGHT is the 'H' EXTENT, measured — never the declared `cap-height`.** oskay's SVGs declare
  500 while their capitals reach 662 (ratio 1.324), so trusting the file engraved every text **32 %
  too tall**; caught by `test_mire_planches`, which measures the engraved laser name. And it is the
  *extent*, not the summit: in the EMS fonts the stroke is the stem's AXIS, so their 'H' runs y=22 to
  652 — taking the summit was 3.4 % short, and stopped matching what a calliper reads on the wood.
- **"Fût contourné" is labelled, not silently shipped.** The Med/Bold variants trace the stem's
  outline, so the machine burns every branch twice — twice the time, a wider trace. Measured: Hershey
  Sans Med's 'H' has 6 strokes against Sans1's 3, i.e. 4.7 strokes per letter against 2.4. **A
  proximity detector was tried and thrown away**: hunting points with another stroke within 6 % of the
  cap gave 27 % for the simplex font against 28 % for the outlined one — it caught junctions, not
  doubling. A figure that separates nothing is worse than none, because it reassures. Christophe asked
  for all 42 knowing this; the label says so.
- **Nothing may vanish silently.** `deplier_texte` + `REPLIS_GLYPHES` substitute the French
  typographic fallback (œ→oe, æ→ae, ß→ss, curly quotes, non-breaking spaces) and **name** whatever is
  left. It runs on BOTH the edge builder and `single_line_text_extent`: if only one applied it, the
  announced bounding box would be narrower than the engraving.

**The gap that motivated all this, now CLOSED**: the shipped `hershey_font.py` had ç, Ç, æ, Æ present
with an **empty** stroke list — "français" engraved "franais", without a word. Regenerated from
`HersheySans1.svg`, which has them. `œ`/`Œ` are absent from *every* oskay font (216 glyphs); only
Relief SingleLine (423) carries them, hence the fallback.

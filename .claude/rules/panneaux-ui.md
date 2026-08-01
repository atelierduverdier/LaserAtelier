---
paths:
  - "task_panels.py"
  - "laser_jobs.py"
---

# Panels: shared UI helpers, the ①②③ convention, jobs

One `TaskPanel*` class per mode (PySide6/Qt). Builds the form, reads widgets, calls `core.*`
generators, writes the file via `_write_gcode_with_dialog`. **Pure UI** — no geometry math beyond
calling core.

## Shared helpers — use them, don't reinvent

- **`_panel_header(form, icon, title)` / `_section(form, title, icon)`** — mode banner & section
  rules (fall back to text if the SVG picto fails, `_icon_pixmap` returns None). `_section` builds a
  `_SectionHeader` full-width "card" (orange left stripe, picto, bold title, ▸/▾ chevron, hover)
  whose open/closed state is **persisted** in the config (`sections` block, keyed by title;
  `_section_state_get/_set`). Buttons are styled panel-wide by a `QPushButton` stylesheet applied to
  `inner` in `_scrollable` — it doesn't touch FreeCAD's own OK/Annuler.
- **`_WrapLabel`** — paragraph label: word-wrap on, **collapses manual `\n` into spaces** (mixing
  both caused stair-stepped text). **Never put an enumeration in ONE `_WrapLabel`** — use
  `_bullet_list(form, items)` (one label per item).
- **`_intro(form, resume, details)`** — short always-visible summary + details folded behind an "En
  savoir plus" toggle. **`_diagram(form, "diag_*.svg")`** — explanatory schematic rows.
- **`_set_row_visible(form, widget, bool)`** — hides label+field together; plain `setVisible` leaves
  orphan labels in a `QFormLayout`.
- **`_PresetController(form, parent, category, fields_getter)`** — preset selector backed by
  `core.factory_presets` (★, non-deletable) + user presets.
- **`_etapes(form, [...])`** — clickable stepper at the top of test panels (jump-to-section).
  **`_verrou(...)`** — lock-by-default on measured fields (also accepts a QTableWidget + buttons).

## Last-session persistence, and the 3 priority levels

Each panel builds `self._last_fields = {key: widget}`, calls `_restore_last_values(key, fields)` at
the end of `__init__` and `_save_last_values` in `accept()` (`_widget_get/_widget_set` handle
combo/checkbox/spin/lineedit).

Shape panels (hatch, filled, curved, flat, curved_cut) also pass `selection=self.selection`: settings
are then written as JSON into a dynamic `LaserAtelierReglages` property on the first selected object
(saved with the .FCStd) and restored with priority over global last values when that object is
selected. **Priority: per-object settings > last values > Preferences defaults.** Pass the selection
kwarg for any new shape-based panel.

In the 4 G-code shape panels AND the test panels (defocus band, power ramp, test grid, kerf), **OK
only saves settings and closes**; generation goes through a dedicated button — "Générer et sauvegarder
le G-code…" (`_on_save_gcode`), `_on_generer` in the ① section of test panels, `_on_creer_test` for
kerf. **The panel stays open after generating** so ② measurements can be typed right after the burn.
`_build_combined_operation` also saves on success, so the combined-job path feeds the per-shape
settings and the tree Job too.

## Test/calibration panel convention (①②③)

Every burn-and-measure mode reads top-to-bottom as:

1. **① Graver** — burn params (Test grid adds an "Objectif" recommended-recipe combo via
   `self._recipes`).
2. **② Entrer les mesures** — data typed **INLINE**: no separate dialog, no trip to Preferences.
   Writes to `save_burn_widths`/`save_shades`/`save_settings`, or computes a value to copy out (kerf,
   offsets).
3. **③ Photo du résultat** — `_make_photo_section`.

Nuancier is the shared ledger (no burn step), so its flow is its own: ① Saisir les tons (table,
lock-by-default) → ② Photo → ③ Graver ce nuancier (planche physique). **Follow this for any new test
mode.**

### ② must never delete what it cannot display (v2.4.0)

`_MesuresPlanchesControleur._on_save` rebuilt the material's whole table from its grids, and
`save_burn_widths` **replaces**. Everything outside the grids was therefore erased on a click of
"Enregistrer les mesures": on the workshop's beech, **27 of 54** defocus measurements — every point
whose power, feed or level fell outside POWERS × FEEDS_DEFOCUS × {15, 36}. Hours of calliper work,
silently, from a button that promises to save. It now merges: only the cells the grids **own** are
replaced, the rest is copied through, and the confirmation says how many off-grid measurements were
kept. Same rule as `_make_largeurs_libres` — **any writer onto `save_burn_widths` must merge.**

`reload` also mapped a point to the *nearest* level grid with **no distance limit**, so a 60 mm
measurement displayed in the "36 mm" grid and the next save rewrote it as 36. Bounded by
`core.SNAP_DEFOCUS_TOLERANCE_MM` now.

The defocus level is free: grids are rebuilt on every `reload()` from
`core.niveaux_defocus_mesures(material)` **plus** the level the host is about to burn
(`get_niveau_cible`, wired to the test grid's "Défocus des cellules"), falling back to
`DEFOCUS_LEVELS_MM` for an unmeasured material. Rebuilding is skipped when the level list is
unchanged — otherwise a refresh would wipe a half-typed row.

### A grid must SAY what it cannot show (v2.28.0)

A defocus grid is created as soon as one measurement exists at that level, but it only has cells
for `POWERS × FEEDS_DEFOCUS`. Points coming from the **power/speed ramp** carry interpolated powers
(S585, S716, S909, S980 on the workshop's beech) — no cell matches, and the grid rendered
completely **empty**. Christophe, on 2026-08-01, in front of a "Défocus 55 mm" table with 20 dashes
in it: *"à quoi sert cela alors ?"*. A fair question about a table that exists **because** of a
measurement it refuses to display.

`lbl_hors_grille[dz]` now lists them under the grid (S/F = width), says they are kept on save, and
adds that a level holding a single power is not an anchor for the model. **Silent when everything
fits** — an always-on warning is noise that stops being read.

This is the display half of the v2.4.0 merge rule below: `_on_save` already *preserved* off-grid
points, but nothing ever *showed* them, so the data was safe and invisible at the same time.

### An objective must burn what ② can accept (v2.3.1)

`TaskPanelTestGrid._recipes` drives the burn through min/max/count spin boxes, and those spread
their steps **linearly**. The ② entry columns are **geometric** (200, 400, 800, 1500, 3000), so no
range can describe them — and nothing checked. `largeurs_foyer` burned F400/1800/3200/4600/6000
against columns 200/400/800/1500/3000 (4 of 5 feeds with nowhere to be typed) and `largeurs_defocus`
burned S400/550/700/850/1000 × F200/650/1100/1550/2000 (3 powers and 4 feeds orphaned). The workshop
had you burn a board and then refused its results.

A recipe may now carry explicit `"powers"` / `"feeds"` lists (passed through to
`build_test_grid_cells`, which uses them instead of the triplet), and **both width objectives derive
theirs from `_MesuresPlanchesControleur.POWERS` / `FEEDS_FOCUS` / `FEEDS_DEFOCUS`** — the alignment
is structural, not a coincidence to maintain. `_appliquer_paliers` locks the six range fields while
such an objective is active and prints the exact values, because a range the job doesn't use is an
interface that lies. Objectives judged by eye (`nuancier_clair`, `decoupe`) keep free ranges: nothing
to align.

Two things the fix's own test caught, both worth keeping in mind: `largeurs_foyer` burned at 0.20 mm
hatch spacing while telling you to measure a single trace with a calliper (the slow/powerful cells
came out as a **solid fill**); and the isolated-trace spacing must clear **1.00 mm**, not the 0.30 of
beech — Sapin is measured at 1.00 mm at focus, softwoods burn far wider, and a spacing tuned on
hardwoods would silently produce an unreadable board on resinous stock.

`_make_photo_section(form, cle_getter, titre)` — reusable "Photo du résultat": a dropdown of ALL
photos for the current `cle_getter()` key (e.g. `"testgrid:MDF"`, `"defocus"`) + a clickable thumbnail
(→ `_show_image_dialog`) + **a free-text description field** (e.g. the defocus/focus level used,
since that isn't reliably inferable from panel state) + add/delete buttons. Returns `{"reload": fn}`
(accepts an optional select index) to call at the end of `__init__` and on material change.

## Power: two mechanisms, one must win

`_make_fluence_widgets` / `_fluence_advice` — the "Puissance vs défocus" section (power compensation
from a measured reference, model F ∝ P/(d·v)). The reference fields are a **calibration**, not job
params: read-only by default (an "Modifier la référence" checkbox unlocks them) so tweaking the job
can't clobber them; `setValue` (restore/presets) still works while locked.

`_appliquer_priorite_nuancier(shade_picker, fluence)` (v1.80.2) enforces which of the two
power-setting mechanisms wins when a nuancier material **and** fluence compensation are both active:
it disables the whole fluence `QGroupBox` **and force-unchecks its checkbox** (disabling alone leaves
an already-ticked box still driving `_effective_fill_power`) whenever
`shade_picker["mat"].currentData()` is truthy.

**Call it as the FIRST statement in the panel's own preview function** (`_update_defocus_preview` /
`_update_style_ui`), never from a separate signal connection — Qt fires same-signal slots in
connection order, and computing effective power before this sync runs would read a checkbox state one
tick stale. Wired into `TaskPanelFilledEngraving` and `TaskPanelCurved` (the two panels with a shade
picker + fluence block); the latter also gained the missing
`combo_mat.currentIndexChanged → _update_style_ui` connection it never had. Root cause this fixed: a
measured S1000 tone silently downgraded to a calculated S529 the moment the fluence checkbox was
ticked, with no visual sign anything had changed.

## The shade picker

`_make_shade_picker(form, on_apply)` — "Nuancier matériau": selecting a tone applies it
**IMMEDIATELY** (same convention as `_PresetController`; a neutral "-- Choisir --" first entry +
blocked signals during reloads prevent accidental applies, e.g. when switching material just to drive
the photo preview), plus a "Voir la photo du nuancier" button enabled only when
`result_photos("nuancier:"+material)` is non-empty.

Since v1.83.0 the list is built from `core.reglages_disponibles(material)` +
`core.grouper_reglages(...)`, so it offers BOTH the nuancier's tones and the burn-width grid's
measured points, under disabled group headers, with a "Classer par" combo
(`core.CRITERES_CLASSEMENT`: noirceur / largeur / defocus). Materials come from the union of
`shade_materials()` and `burn_width_materials()` — a material with widths but no judged tone used to
be invisible.

**Do NOT copy the grid into the nuancier to achieve this**: grid points carry no darkness, so a copy
would have to invent one (they're nearly all black), skewing `darkness_fluence_curve` and hence
calibrated photo engraving and "ton sur mesure"; it would also add ~50 rows to a beech nuancier of 83
the user already finds unreadable. Reading both tables live also makes the sync free.

`_PastilleReglage` / `_choisir_reglage_visuel(parent, combo_shade, material, critere)` — the visual
face of the picker: one clickable disc per setting, tinted from its MEASURED darkness with the same
`255 - d*255` convention the halftone preview uses. Two rules hold it together:

1. **The grid is built from the combo's own items, never from a second `reglages_disponibles` call** —
   that makes identical grouping/order/content structural rather than something to keep in sync, and
   a measurement saved between the two reads can't make the click apply a different setting than the
   disc showed.
2. **It returns an INDEX and lets the combo replay it.** PySide round-trips item data through a
   QVariant and rebuilds a NEW dict on every `itemData()` call, so two reads of one item are never the
   same object — matching by identity fails silently, and the index is the only reliable handle.
   (Tests must compare item data with `==`, never `is`.) Setting the same index emits no signal, so
   `_on_visuel` calls `_apply()` directly in that case.

A grid point has no judged darkness (`darkness is None`): its disc is **HATCHED**, never painted a
made-up grey — same reasoning as `reglages_disponibles` keeping None. Its caption falls back to the
measurement that does exist (the calliper width), so sorting by darkness doesn't produce a block of
identical hatched discs all labelled "-- %".

## The physical swatch board

`_nuancier_geometrie(n_items, colonnes, n_lignes)` — layout of the PHYSICAL board (Ø14 circle per
tone): drawing constants, chosen columns/rows, frame size. **SINGLE SOURCE**, called both by
`_construire_nuancier_preregles` (which builds the geometry) and by the panel's size preview — a
preview recomputing the layout on its own starts lying the moment a constant changes here (exactly
what happened to the ramp graduations). Column count is a user setting since v1.84.0
(`NUANCIER_COLONNES_DEFAUT = 10`, was hardcoded at 5): past a few dozen tones, 5 columns give a
narrow, very tall strip that wastes stock. `n_lignes` is the label's line count — both callers derive
it from the items they already hold, so it can't silently disagree with what gets drawn.

**The circle diameter is what caps the label width** (`cell_w = DIAM + GAP_X`), so the two must be
judged together: at Ø20 with a one-line label, `"100% S1000 F1000"` needed 58 mm in a 27 mm cell, hit
the 2.2 mm legibility floor, and **still overflowed onto its neighbour — 89 of the 117 measured tones
collided** (v1.84.1). Fixed by stacking the label on 3 lines in `_nuancier_items` (14 mm block) and
dropping to Ø14: 83 beech tones went 292 × 348 mm → 232 × 322 mm with 8.6 mm of clearance. Below the
floor the drawing code truncates rather than overflowing — overlapping labels are worse than a clipped
one. **Verify label changes on the BUILT board's edge bounding boxes, never on the layout formula**:
the overflow existed for months precisely because nothing measured the geometry that came out.

## Reprendre la sélection (v2.10.0)

`_reselect_button(form, on_reselect, selection_courante=None)` — a panel captures the 3D selection at
**open** time only; this button re-reads it. It existed in four of the five selection panels for a
long time. Two things were wrong with that:

- **Hachures didn't have it at all**, so "everywhere" was false.
- **It didn't announce itself.** On 2026-07-31 the user asked for the feature while it was sitting in
  the panel he had open. A button among fifteen others is invisible when you don't know it exists.

Passing `selection_courante` (a getter for what the panel holds) adds a live status line above the
button: grey "identique" with the button disabled, red "N objets — différente" with it enabled.
`_signature_selection` compares `(Object.Name, SubElementNames)` sorted — so it catches a different
sub-element on the same object, and ignores click order. It reads **names only, never geometry**, so
polling it every 600 ms costs nothing; re-reading the geometry stays behind the click.

**Deliberately NOT automatic.** Re-applying a selection also re-applies the per-shape settings stored
on the object (`LaserAtelierReglages`), which would overwrite what the user has just typed, silently
— and on a big model each re-read rebuilds the ray probe. The user chose the button for exactly that
reason. If this is ever revisited, keep geometry and settings separable.

## Job combiné

Operations are NOT added via bespoke mini-dialogs. Each combinable mode (Flat cut, Curved cut, Curved
marking, Test grid) has a `_build_combined_operation()` returning `{type, label, params}` (params =
the exact kwargs its own generator uses, full-featured) and a
`_combined_add_button(form, self._on_add_to_combined)` that appends to the module-level list
`_COMBINED_OPS` (in-memory: params carry Part edges/probe, not JSON-serializable). `TaskPanelCombined`
reads `_COMBINED_OPS` (its `self.operations` IS that list), reorders/removes/clears, and generates.
**Reuse this pattern for any new combinable mode** instead of a simplified duplicate dialog.

## `laser_jobs.py` — the tree Job objects

Level 2 of per-shape settings. One `App::FeaturePython` per (mode, main source) couple,
created/updated by `_save_last_values` via `creer_ou_maj_job(mode, sources)`. The Job holds `Mode`
(hidden key) and `Sources` (LinkList — curved modes reference motif + 3D model); **the SETTINGS stay
on the source shape** (`LaserAtelierReglages`, level 1) — the Job is a bookmark, not a second source
of truth. `VueJobLaser.doubleClicked` re-selects the sources and reopens the mode's panel pre-filled
(`ouvrir_job`). Proxies carry no state (dumps/loads return None); regenerating updates the existing
Job (user-renamed Labels are preserved).

## Face construction & fill-geometry memo (perf, v1.79.3)

`FaceMakerBullseye`'s O(n²) nesting sort costs ~10.5 s on a 179-wire imported SVG trace, **twice** per
fill (rebuild + inset). For ≥12 wires `_faces_from_any_shape` first tries
`_faces_rapides_depuis_fils` (laser_core), a Bullseye-free builder: pure-Python even-odd nesting on
re-polygonized wires (0.02 mm deflection), self-intersecting wires repaired solo via `fix()` — which
splits them, as Bullseye did silently; **signed area is used ONLY for orientation** (a bowtie has
near-zero signed area yet real coverage) — then faces assembled as
`Part.Face([outer CCW] + [holes CW])`: **explicit orientation is mandatory**, without it holes ADD to
the area instead of subtracting. Final sanity = non-empty tessellation + area coherence; any doubt
returns None → Bullseye fallback. `isValid()` may stay False on tangent wires without harming the
pipeline — **the empirical gate is tessellation** (measured: identical 9098 hatch edges, 0.4 s vs
10.5 s). XY-plane only; other planes go straight to Bullseye.

The filled-engraving panel memoizes the last built geometry (`_MEMO_REMPLISSAGE`, key = selection
Names + `Shape.hashCode()` + subelements + spacing/angle/inset/perimeter): photo-preview iterations
and the final generation reuse faces/edges — tone/power changes don't touch geometry, so re-renders
drop from ~30 s to <1 s on heavy traces.

**Projection (v1.79.5)**: `run_projection` projects EACH motif into its OWN sub-compound
(`Part.Compound` of per-motif compounds) and `_faces_from_any_shape` recurses into sub-compounds —
fill parity (even-odd) must be computed **PER source path then overlaid**, like an SVG renderer;
merging all edges into one flat compound recomputed parity globally and flipped regions (measured
−59 % filled area on the imported skull). Second, stacked bug: `discretize(Distance=d)` returns a
SINGLE point for edges shorter than ~d/2, and `drop_edges_to_surface` silently dropped them —
puncturing wire loops (a 21 000 mm² background face vanished). Sub-d edges now fall back to their two
Vertexes. Legacy flat-compound objects keep the old global behaviour — re-run the projection to heal
them.

**G-code generation had its own freeze (v1.79.4)**: with no 3D reference, `generate_gcode_curved`
builds `_IDWHeight(all_pts)` over EVERY discretized point (~150k on a dense fill) and each
`z_at(x,y)` rebuilt a full distance list (~25 ms) — called once per transit step, so ~9k transits
froze the GUI for many minutes to interpolate… a constant (flat work has all z equal). `_IDWHeight`
now detects the constant-Z cloud in `__init__` and answers O(1); relief clouds keep the exact original
IDW. Measured: skull fill G-code 0.6 s vs >10 min. When profiling generation, remember
`heapq.nsmallest` shows up as cheap per call — the cost is the list comprehension feeding it.

## A brand-new section must open (2026-08-01)

`_activer_sections` read the stored fold state with a hardcoded fallback: `_section_state_get(cle,
False)`. The `ouvert` argument `_section` accepts was therefore **never honoured**, and a section
that nobody has ever folded — because it has only just come into existence — was born closed.

Every new control inherits that: it exists, it is correctly wired, it passes its tests, and the
user cannot find it. This happened **three times in one day**: the Planche 2b button, then the
mire checkbox, which Christophe searched for and reported missing both times. A control the user
cannot find is a control that does not ship.

The fallback is now the caller's own `ouvert`. Two rules follow:

- A section holding the entry point of a new workflow gets `ouvert=True`. It opens the first time,
  because no stored state exists for a name that has never existed.
- A section the user has folded **himself** stays folded — that is his choice and it wins. Only the
  absence of a stored state is filled by the caller's default.

Don't bury a new feature in an existing section either: the user may have folded that one years
ago, and your addition silently inherits the fold. §7 of `test_noirceur_photo.py` freezes both
halves — it was verified to go red with the old hardcoded `False`.

## The accordion must not fold the ①②③ steps (2026-08-01)

Opening any section folded all the others — including the numbered **step** sections, which are
not detail: they carry the mode's actions. The Grille de test's **"Générer et sauvegarder le
G-code"** button lives in ①, so touching any setting made the panel's primary action vanish.
Christophe looked for it and could not find it — the *fourth* time in one evening that something
was hidden behind a fold.

Sections whose title starts with ① ② ③ are now skipped by the accordion, and open by default when
no state is stored. They can still be folded **by hand**; it is the automatic fold, that nobody
asked for, that is gone.

The stored `False` for those sections was not a choice either — it was the defect's residue.
`_depiler_etapes_une_fois()` clears it **once**, behind a marker key, touching only step keys.
Anything folded after that was folded by a real click and stays folded; §12 checks both halves,
including that a second run does not re-open a deliberate fold.

Rule of thumb for this panel family: **the button that produces the deliverable never lives behind
a fold that something else can close.**

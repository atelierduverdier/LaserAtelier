# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **FreeCAD workbench** (FreeCAD 1.1) that turns 2D/3D geometry into LinuxCNC G-code for a
diode-laser head mounted on a CNC (marking, filled engraving, multi-pass cutting, test grids,
calibration strips). The repository **is** the workbench directory — it is cloned directly into
FreeCAD's `Mod` folder:

```bash
git clone <repo> ~/.local/share/FreeCAD/<version>/Mod/LaserAtelier   # e.g. v1-1
```

There is **no build system, no linter, no CI, and no test framework**. FreeCAD loads the `.py`
files directly at startup.

## Language convention (important)

Everything user-facing and in-source is **French**: code comments, docstrings, UI strings,
tooltips, generated G-code comments, and **git commit messages**. Keep new code in French to
match. (This CLAUDE.md is the exception.)

## Versioning

Single source of truth: `VERSION` in `laser_core.py` — shown in every panel banner (next to the
chapeau signature) and stamped as the first line of every written G-code (`_write_gcode_with_dialog`).
Bump it **together** with `<version>`/`<date>` in `package.xml` (FreeCAD Addon Manager metadata),
the hero badge in `docs/index.html`, and the version line under the README logo. Tag releases
`v<version>` on main.

## Working / verifying changes

- **Syntax check** (do this after every edit — it's the only automated gate):
  ```bash
  python -c "import ast; [ast.parse(open(f).read()) for f in ('laser_core.py','task_panels.py','commands.py','InitGui.py')]"
  ```
- **Headless unit-testing of `laser_core.py`** — the established pattern, since FreeCAD isn't
  importable outside the app. Stub the FreeCAD modules before importing:
  ```python
  import sys, types
  fc = types.ModuleType("FreeCAD")
  fc.getUserAppDataDir = lambda: "/tmp/whatever"
  fc.Console = types.SimpleNamespace(PrintMessage=lambda m: None, PrintWarning=lambda m: None)
  class Vector:
      def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = float(x), float(y), float(z)
  fc.Vector = Vector
  sys.modules["FreeCAD"] = fc
  sys.modules["Part"] = types.ModuleType("Part")   # stub, or monkeypatch the few Part uses
  import laser_core as core
  ```
  For functions that touch real `Part` geometry (`build_test_grid_cells`, `generate_hatch_edges`,
  `build_filled_engraving_edges`, `text_to_edges`), monkeypatch the specific helper
  (`core.chain_edges`, `core.generate_hatch_edges`, `core.text_to_edges`) or `core.generate_gcode_curved`
  to capture arguments, rather than reimplementing OpenCascade. Assert on the produced G-code string.
- **`task_panels.py` CAN be exercised headless** (system PySide6 is available outside FreeCAD):
  stub `FreeCAD` (Vector also needs `distanceToPoint`/`isEqual`), `FreeCADGui`
  (`Selection.getSelectionEx` classmethod returning a controllable list — keep it EMPTY when
  instantiating panels, fake shapes lack `BoundBox`), and `Part`
  (`LineSegment(+toShape→edge with discretize(Distance=…))`, `Wire`/`Face`/`Compound` as identity
  lambdas), monkeypatch `core.generate_hatch_edges = lambda *a: []`, create a `QApplication`, then
  instantiate every `TaskPanel*` — catches wiring errors without launching FreeCAD. Visibility
  asserts need `isVisibleTo(parent)` (plain `isVisible()` is False offscreen). Final visual check
  still means the user restarting FreeCAD.
- The repo lives in the user's `Mod` dir; a **FreeCAD restart** picks up changes. Commit + push are
  routine for this personal project.

## Architecture

Five modules, cleanly layered — keep the layering:

- **`laser_core.py`** (~4.5k lines): ALL geometry + G-code logic. **No Qt** (the photo mode's
  QImage→darkness-grid conversion lives in the panel; core takes plain float grids). This is where
  generators, the defocus model, the vector font, config persistence, and geometry helpers live.
  Organized into banner-commented sections, one per mode. This is the layer you unit-test headless.
  Notable shared sections beyond the per-mode generators: STYLES DE TRAIT (curvilinear helpers
  `_chain_cumlen`/`slice_chain`/`dash_chain`/`dot_positions`/`wave_resample`, used by stroke styles
  AND cutting tabs), fluence (`line_fluence`/`power_for_line_fluence`), the measured-tones nuancier
  (`load_shades`/`shade_for_darkness`), factory presets (`_FACTORY_PRESETS`/`all_presets`), and
  centralized machine settings (`Z_WORK_MM`, `TRANSIT_MARGIN_MM`, `SPOT_FOCUS_MM`… via
  `_USER_SETTINGS`; panels read these instead of exposing their own Z fields — cutting modes keep
  per-job Z because nozzle height is thickness-dependent safety).
- **`task_panels.py`** (~5.5k lines): one `TaskPanel*` class per mode (PySide6/Qt). Builds the form,
  reads widgets, calls `core.*` generators, writes the file via `_write_gcode_with_dialog`. Pure UI;
  no geometry math beyond calling core. Shared UI helpers (use them, don't reinvent):
  - `_panel_header(form, icon, title)` / `_section(form, title, icon)` — mode banner & section rules
    (fall back to text if the SVG picto fails, `_icon_pixmap` returns None). `_section` builds a
    `_SectionHeader` (full-width "card": orange left stripe, section picto, bold title, ▸/▾ chevron,
    hover) whose open/closed state is **persisted** in the config (`sections` block, keyed by title;
    `_section_state_get/_set`). Buttons are styled panel-wide by a `QPushButton` stylesheet applied to
    `inner` in `_scrollable` (rounded, orange border on hover) — doesn't touch FreeCAD's OK/Annuler.
  - `_WrapLabel` — paragraph label: word-wrap on, **collapses manual `\n` into spaces** (mixing both
    caused stair-stepped text). Never put an enumeration in ONE `_WrapLabel` — use
    `_bullet_list(form, items)` (one label per item) instead.
  - `_intro(form, resume, details)` — short always-visible summary + details folded behind an
    "En savoir plus" toggle. `_diagram(form, "diag_*.svg")` — explanatory schematics rows.
  - `_set_row_visible(form, widget, bool)` — hides label+field together (plain `setVisible` leaves
    orphan labels in a QFormLayout).
  - Last-session persistence: each panel builds `self._last_fields = {key: widget}`, calls
    `_restore_last_values(key, fields)` at end of `__init__` and `_save_last_values` in `accept()`
    (`_widget_get/_widget_set` handle combo/checkbox/spin/lineedit). Shape panels (hatch, filled,
    curved, flat, curved_cut) also pass `selection=self.selection`: settings are then written as
    JSON into a dynamic `LaserAtelierReglages` property on the first selected object (saved with
    the .FCStd) and restored with priority over global last values when that object is selected.
    Priority: per-object settings > last values > Preferences defaults. Pass the selection kwarg
    for any new shape-based panel. In the 4 G-code shape panels (filled/curved/flat/curved_cut)
    AND the test panels (defocus band, power ramp, test grid, kerf), **OK only saves settings and
    closes**; generation goes through a dedicated button — "Générer et sauvegarder le G-code…"
    (`_on_save_gcode` on shape panels, `_on_generer` in the ① section of test panels; kerf's is
    "Créer le test dans le document", `_on_creer_test`). The panel stays open after generating so
    ② measurements can be typed right after the burn.
    `_build_combined_operation` also saves on success, so the combined-job path feeds the
    per-shape settings and the tree Job too.
  - `_PresetController(form, parent, category, fields_getter)` — preset selector block backed by
    `core.factory_presets` (★, non-deletable) + user presets.
  - `_make_fluence_widgets` / `_fluence_advice` — "Puissance vs défocus" section (power compensation
    from a measured reference, model F ∝ P/(d·v)). The reference fields are a **calibration**, not job
    params: read-only by default (an "Modifier la référence" checkbox unlocks them) so tweaking the
    job can't clobber them; `setValue` (restore/presets) still works while locked.
  - `_make_shade_picker(form, on_apply)` — "Nuancier matériau" block: selecting a tone in the
    combo applies it IMMEDIATELY (same convention as `_PresetController`; a neutral "-- Choisir --"
    first entry + blocked signals during reloads prevent accidental applies, e.g. when switching
    material just to drive the photo preview), plus a "Voir la photo du nuancier" button, enabled
    only when `result_photos("nuancier:"+material)` is non-empty, to compare against the real
    engraved board before picking a tone.
  - `_make_photo_section(form, cle_getter, titre)` — reusable "Photo du résultat" section: a
    dropdown of ALL photos for the current `cle_getter()` key (e.g. `"testgrid:MDF"`, `"defocus"`) +
    a clickable thumbnail (→ `_show_image_dialog`) + a free-text description field (e.g. the
    defocus/focus level used, since that isn't reliably inferable from panel state — see
    `set_photo_description`) + add/delete buttons. Returns `{"reload": fn}` (accepts an optional
    select index) to call at end of `__init__` and on material change. Backed by core photo
    helpers (see persistence).
  - **Test/calibration panel convention (①②③)**: every burn-and-measure mode reads top-to-bottom
    as **① Graver** (burn params; Test grid adds an "Objectif" recommended-recipe combo via
    `self._recipes`) → **② Entrer les mesures** (data typed INLINE — no separate dialog, no trip to
    Preferences; writes to `save_burn_widths`/`save_shades`/`save_settings` or computes a value to
    copy out for kerf/offset) → **③ Photo du résultat** (`_make_photo_section`). Each such panel
    also carries an `_etapes(form, [...])` clickable stepper at the top (jump-to-section) and a
    `_verrou(...)` lock-by-default on its measured fields (also accepts a QTableWidget + buttons).
    Nuancier is the shared ledger (no burn step), so its ①②③ is its own flow: ① Saisir les tons
    (table, lock-by-default) → ② Photo → ③ Graver ce nuancier (planche physique). Follow this for
    any new test mode.
  - **Job combiné**: operations are NOT added via bespoke mini-dialogs anymore. Each combinable mode
    (Flat cut, Curved cut, Curved marking, Test grid) has a `_build_combined_operation()` returning
    `{type,label,params}` (params = the exact kwargs its own generator uses, full-featured) and a
    `_combined_add_button(form, self._on_add_to_combined)` that appends to the module-level list
    `_COMBINED_OPS` (in-memory: params carry Part edges/probe, not JSON-serializable). `TaskPanelCombined`
    reads `_COMBINED_OPS` (its `self.operations` IS that list), reorders/removes/clears, and generates.
    Reuse this pattern for any new combinable mode instead of a simplified duplicate dialog.
- **`laser_jobs.py`**: the tree "Job" objects (level 2 of per-shape settings). One
  `App::FeaturePython` per (mode, main source) couple, created/updated by
  `_save_last_values` via `creer_ou_maj_job(mode, sources)`. The Job holds `Mode` (hidden key)
  and `Sources` (LinkList — curved modes reference motif + 3D model); the SETTINGS stay on the
  source shape (`LaserAtelierReglages`, level 1) — the Job is a bookmark, not a second source of
  truth. `VueJobLaser.doubleClicked` re-selects the sources and reopens the mode's panel
  pre-filled (`ouvrir_job`). Proxies carry no state (dumps/loads return None); regenerating
  updates the existing Job (user-renamed Labels are preserved).
- **`svg_import.py`**: standalone SVG-to-geometry importer — parses a `.svg` file directly (stdlib
  `xml.etree.ElementTree`, no Draft/DXF detour) into one `Part::Feature` per top-level `<path>`
  element (`Shape = Part.Compound(edges)`, matching the bare-edge-compound convention
  `_faces_from_any_shape`/`chain_edges` already handle from Draft's own SVG/DXF import), with
  `ViewObject.LineColor` set from the path's resolved fill (inherited from ancestor `<g>`s per
  normal SVG cascade; `style=` beats `fill=`; `fill="none"` falls back to the element's own
  stroke, else black). The path-grammar/Bezier-and-arc-flattening/transform/color layer is **pure
  Python with zero FreeCAD import at module level** — deliberately, so it's unit-testable with no
  stubbing at all; only the object-creation functions (`_subpath_to_edges`, `_record_to_object`,
  `import_svg_file`) import `FreeCAD`/`Part`, locally inside themselves. No true OCCT Bezier/Arc
  edges anywhere (matches the rest of the codebase): curves are flattened to short
  `Part.LineSegment` chains. `FLATTEN_TOL_MM = 0.02` is a max chord DEVIATION (sagitta), not a
  point spacing — well under the burn width, so no visible faceting even on large gentle curves;
  and since `chain_edges` re-densifies segments at 0.3 mm spacing for G-code anyway, the finer
  import fidelity costs nothing downstream.
  One `doc.recompute()` for the whole file — that's what makes it fast versus the fragmented DXF
  detour. `<use>`, gradients, `<clipPath>`/`<mask>`/`<filter>`, embedded raster `<image>`, and CSS
  class-selector cascading are out of scope — skipped with a collected `FreeCAD.Console.PrintWarning`,
  never a hard failure.
- **`commands.py`**: one `*Command` class per mode (`GetResources`/`IsActive`/`Activated`) that opens
  the matching task panel via `_show(panel)` (closes any active task dialog first — FreeCAD refuses a
  second one otherwise); `register_commands()` registers them all.
- **`InitGui.py`**: the `Workbench` class — toolbar/menu order (`command_list`), lazy imports in
  `Initialize()`. Runs at FreeCAD startup.

**Fast face construction & fill-geometry memo** (perf work, v1.79.3): `FaceMakerBullseye`'s O(n²)
nesting sort costs ~10.5 s on a 179-wire imported SVG trace, twice per fill (rebuild + inset). For
≥12 wires `_faces_from_any_shape` first tries `_faces_rapides_depuis_fils` (laser_core), a
Bullseye-free builder: pure-Python even-odd nesting on re-polygonized wires (0.02 mm deflection),
self-intersecting wires repaired solo via `fix()` — which splits them, as Bullseye did silently;
signed area is used ONLY for orientation, a bowtie has near-zero signed area yet real coverage —
then faces assembled as `Part.Face([outer CCW] + [holes CW])`: explicit orientation is mandatory,
without it holes ADD to the area instead of subtracting. Final sanity = non-empty tessellation +
area coherence; any doubt returns None → Bullseye fallback. `isValid()` may stay False on tangent
wires without harming the pipeline — the empirical gate is tessellation (measured: identical 9098
hatch edges, 0.4 s vs 10.5 s). XY-plane only; other planes go straight to Bullseye (same in
`inset_face_robuste`, which reuses the known `face.OuterWire`+holes structure instead of re-sorting).
The filled-engraving panel memoizes the last built geometry (`_MEMO_REMPLISSAGE` in task_panels,
key = selection Names + `Shape.hashCode()` + subelements + spacing/angle/inset/perimeter): photo-
preview iterations and the final generation reuse faces/edges — tone/power changes don't touch
geometry, so re-renders drop from ~30 s to <1 s on heavy traces. **Never test novel OCC call
patterns in the user's live session**: a per-wire `makeOffset2D` experiment segfaulted the whole
GUI (losing unsaved work); run risky probes with `freecadcmd` on a document copy in the scratchpad.
Projection (v1.79.5): `run_projection` projects EACH motif into its OWN sub-compound
(`Part.Compound` of per-motif compounds) and `_faces_from_any_shape` recurses into sub-compounds —
fill parity (even-odd) must be computed PER source path then overlaid, like an SVG renderer;
merging all edges into one flat compound recomputed parity globally and flipped regions (measured
−59 % filled area on the imported skull). Second, stacked bug: `discretize(Distance=d)` returns a
SINGLE point for edges shorter than ~d/2, and `drop_edges_to_surface` silently dropped them —
puncturing wire loops (a 21 000 mm² background face vanished; face holes were swallowed). Sub-d
edges now fall back to their two Vertexes. Legacy flat-compound objects keep the old global
behavior — re-run the projection to heal them. `ViewObject` guards must use
`getattr(obj, 'ViewObject', None) is not None`: in freecadcmd the attribute EXISTS but is None,
so `hasattr` lets an AttributeError through.
G-code generation had its own freeze (v1.79.4): with no 3D reference, `generate_gcode_curved`
builds `_IDWHeight(all_pts)` over EVERY discretized point (~150k on a dense fill) and each
`z_at(x,y)` rebuilt a full distance list (~25 ms) — called once per transit step, so ~9k transits
froze the GUI for many minutes to interpolate... a constant (flat work has all z equal). `_IDWHeight`
now detects the constant-Z cloud in `__init__` and answers O(1); relief clouds keep the exact
original IDW. Measured: skull fill G-code 0.6 s vs >10 min. When profiling generation, remember
`heapq.nsmallest` shows up as cheap per call — the cost is the list comprehension feeding it.

**Adding a mode** touches all four: a generator in `laser_core`, a panel in `task_panels`, a command
in `commands.py` (+ `register_commands`), an entry in `InitGui.py`'s `command_list` (grouped by theme
with `"Separator"` tokens), and an SVG in `resources/icons/` (64×64, orange `#ff8a00` + slate
`#2f3540` house style; `sect_*.svg` are the small section pictos reused across panels). A
self-contained subsystem may keep its generator-equivalent logic in its own sibling module instead
of `laser_core.py` — `laser_jobs.py` and `svg_import.py` are the two such exceptions — but it still
touches the same panel/command/`InitGui`/icon integration points. Every mode
icon carries the **chapeau signature** (a small bowler hat, bottom-right corner, `class="chapeau-verdier"`
group — copy it from any marked icon or from `chapeau.svg`, the full-size standalone source); add it
to new mode icons, keep it out of `sect_*.svg` and `diag_*.svg`. Mode icons are mirrored in
`docs/assets/` for the doc site — sync the copy when an icon changes. SVG gotcha: QtSvg silently
renders NOTHING if the XML is invalid (e.g. `--` inside a comment) — validate with `xmllint --noout`.

### G-code generation contract

Generators are `generate_gcode_*(...)` in `laser_core.py`, each returning a **sanitized G-code
string or `None`** (None = empty geometry). Shared conventions:

- **Three dialects** via the per-laser-profile setting `gcode_dialect` (`GCODE_DIALECT`, default
  `"linuxcnc"`): `_apply_settings_config` derives everything — for `"grbl"`/`"grblhal"` it empties
  `SPINDLE_SELECT`, swaps `CMD_ARM` to the M4 (laser-mode) variant, and `cmd_path_blend()` returns
  None instead of `"G64"` (they blend natively via `$11`). `cmd_tool_comp()` becomes a comment for
  `"grbl"` only; `"grblhal"` keeps T/M6 + G43 H (tool table compiled in, `N_TOOLS`).
  Never emit `$n` / `T`/`M6` / `G43` / `G64` literals directly — always go through
  `SPINDLE_SELECT` / `cmd_tool_comp()` / `cmd_path_blend()`. The sanitizer also strips trailing
  spaces (empty `{sel}`). The mixed mill+laser offset-test generator is knowingly LinuxCNC-only.
- **LinuxCNC RS274 dialect**: laser is spindle `$1` (`SPINDLE_SELECT`); header is
  `G21/G90/G94/T<n> M6/G43 H<n>` (`cmd_tool_comp()` — a function, not a constant, so it follows the
  `LASER_TOOL` preference, default 100, set per laser profile) then `M5 $1`; arm once with `CMD_ARM`
  (`M3` at zero power + dwell), power per segment via `S…` (`CMD_BEAM_ON/OFF`), disarm `M5`, end
  `M2`. Power fields are scaled 0..`S_MAX` (preference `s_max`, default 1000 — panels use
  `setRange(0, core.S_MAX)`, never a hard-coded 1000). The emitted `T<n> M6` loads the laser tool
  itself (no-op if already loaded; prompts once under manual tool change) and `G43 H<n>` applies its
  X/Y offsets (tool.tbl) + probed Z.
- **`sanitize_gcode_for_linuxcnc(text)`** is applied at every generator's return, and is required:
  LinuxCNC rejects **nested parentheses** in comments (`passe(s)`, `(par bande de Z)`) and **non-ASCII
  bytes** (French accents). The sanitizer brackets inner parens and transliterates accents. It is
  idempotent (safe for combined jobs that re-wrap sub-bodies).
- **`body_only=True`** omits header/arming/footer so a body can be embedded in a combined job with a
  single arm/disarm (see `generate_gcode_combined`). **`frame_only=True`** emits only the bounding
  rectangle (a separate framing-check file). **`min_safe_z`** imposes a common retract floor so
  stacked operations don't plunge at the wrong height (`_operation_intrinsic_safe_z`).
- **`TRAVEL_CLEARANCE_MM`** is the flyover margin over the work Z for transits. On flat work it should
  be small/0 — lifting per hatch line is the classic wasteful bug; transit at the working Z, laser off.
- **Stepped-ramp generators** (`generate_gcode_power_ramp_lines`, defocus calibration band) draw
  tick/graduation marks that must land on the trajectory the G-code ACTUALLY follows, not a naive
  continuous interpolation. The moved axis (X) and the ramped value (Z or S) are often parametrized
  differently across the same `n_steps`/`k` loop (e.g. `x1 = length*(k+1)/n_steps` vs
  `t = k/(n_steps-1)`), so a plain `x = length*(target-start)/(end-start)` formula silently lands a
  tick one step early/late. Reconstruct the `(x, value)` breakpoints exactly like the generation
  loop and interpolate within those, and check the result against an actually-generated `.ngc` file
  — a headless test that only re-derives the same formula will pass while still being wrong (bug
  fixed in v1.71.5 after the user caught it on a real file).

### Defocus model (used by filled-engraving, defocus fill, calibration)

A linear divergence cone calibrated from **two real measurements** (never guessed):
`defocus_divergence_half_angle(d_focus, d_calib, z_calib)` → `spot_diameter_at_defocus(z, …)` →
`defocus_for_fill_spacing(spacing, …)`. The **fill is inset by the spot radius** so the burn stays
inside the outline (`fill_inset` in `build_test_grid_cells` / `build_filled_engraving_edges`,
via square inset or `Part.Face.makeOffset2D(-r)`; `inset_face_robuste` re-polygonizes wires first —
OCC segfaults on some imported BSplines — and rebuilds the polygonal face DIRECTLY from the known
structure (`face.OuterWire` CCW + holes CW by signed area, XY plane only; other planes keep the old
Bullseye build): `FaceMakerBullseye`'s O(n²) nesting sort costs ~11 s for nothing on a ~180-wire
face whose structure is already known. On offset failure it discriminates by `Area >
2·perimeter·inset`: a genuinely thin stroke is skipped as before (the contour blackens it), but a
LARGE face OCC chokes on — e.g. an imported SVG path rebuilt as one face with ~200 hole wires,
where the offset returns null wholesale — falls back to filling WITHOUT inset plus a console
warning, instead of silently producing an empty fill, which the panel then reported as the
misleading "Rien à afficher (aucun trait)"). When a
contour is drawn, the filled-engraving panel (`TaskPanelFilledEngraving._fill_inset`) reduces that
inset by the **contour's burn radius** so the fill deliberately tucks *under* the contour (re-burned
at focus on top) — closing the pale liseré left at the edge, most visible at high defocus where the
optical spot over-estimates the real burn width. Outward overspill is bounded by the contour radius so
it stays hidden; a wider contour closes more of the gap.

The **measured** burn width (which drives fill spacing/inset, not the optical spot) is
`burn_width_defocus_scaled(power, feed, defocus)` — **feed-aware** since v1.31.0. Calibration is
burned via three separate planks (`generate_gcode_planche_focus` / `_defocus` / `_spot`, all
translated to piece zero on write): Planche 2 burns an S×F grid at **each** `DEFOCUS_LEVELS_MM`
level (15 and 36 mm), and `burn_width_defocus_scaled` interpolates **bilinearly in (S, F)** at each
level (shared `_bilinear_burn` helper, same as `burn_width_at` at focus: S linear, F log) then
linearly between the two bracketing levels. **Below** the lowest measured level it interpolates
between the directly-measured **focus** table and that level (v1.80.0) — the fill's own defocus is
only a couple tenths of a mm (0.10 mm for a 0.26 mm spacing), and down there the burn is governed by
heating time, not optics. Extrapolating the optical cone to z≈0 over-estimated it **2.1×** on beech
(0.21 mm announced for 0.10 mm measured), so hatches the workbench believed solid came out striped.
Only above the highest level (or with no focus table) does it still
fall back to the proportional-to-optical-spot extrapolation. Measurements are entered inline in the
Test-grid panel's "② Entrer les mesures" section (`_GrilleResultats` per plank/level, lock-by-default;
stored with each point's `z_offset`, snapped to the nearest standard level by `_snap_defocus_level`
on read — e.g. legacy 15.34 → 15; legacy single-feed data lands in the F800 column). This replaces
the earlier single-point average that over-estimated the burn at a working defocus (e.g. 36 mm) far
from the one measured point (~15 mm) — the root cause of the liseré that v1.11.2 could only mask
with the contour.

**Always pass `material` to the burn-width functions.** `_burn_width_material(None)` only guesses
when *exactly one* material has been measured; with two or more it returns `None`, and every caller
silently degrades — `burn_width_defocus_scaled` returns `None`, `_build_edges` skips the correction
entirely, and the hatch keeps the requested spacing however narrow the real trace is. That is how a
beech fill at S200/F1800 (0.10 mm burned, 0.26 mm spacing → 62 % bare wood) shipped as G-code the
workbench believed solid. `TaskPanelFilledEngraving._materiau()` (v1.80.0) feeds the "Nuancier
matériau" combo into all five of its calls; other panels still rely on the single-material guess.

The same panel now answers "will this fill be **solid**?" out loud: `_maj_recouvrement` compares the
measured burn to the hatch spacing and colours `lbl_recouvrement` green (covered) or amber (striped).
When it's striped it names the cost of the automatic tightening *and* suggests the fastest measured
setting whose trace covers the spacing (`core.reglage_couvrant_le_pas`) — widening the trace is
almost always better than tripling the line count. That search is **defocus-aware** (v1.80.1): the
spacing itself sets the defocus (0.90 mm spacing → 13 mm of lift), and a trace that measures 0.30 mm
at focus measures 1.0 mm up there, so candidates are the (S, F) couples measured at the level
*nearest the working defocus* — focus table near zero, defocus table beyond — then scored with the
same interpolator as the verdict, so suggestion and verdict can never contradict each other. Decorative fill styles (dashes, dots, wave) skip
the check: their gaps are the point.

### Persistence & user settings

Single JSON file `laser_atelier_config.json` in FreeCAD's user app-data dir
(`load_config`/`save_config`). Holds: material `presets_*`, `nozzle` profile, per-mode pre/post
G-code, a `settings` block, laser profiles (`lasers` + `active_laser`), and a `photos` block
(key → LIST of `{"file": relative filename, "description": free text}`; an old single-string value
or a bare list of filenames is migrated on read by `_photo_list`). **Result photos** (several per
test/calibration key) live in a `photos_resultats/` subdir of the **workbench
dir** (`_WORKBENCH_DIR`, next to the code so they survive deleting the original; gitignored;
migrated once from the old `app-data/laser_atelier_photos`); core helpers `photos_dir`/
`result_photos`/`add_result_photo`/`set_photo_description`/`delete_result_photo` (the last takes an
optional filename; None clears all) copy/list/describe/forget them (no Qt — the panel paints the
thumbnail and hosts a free-text description field, since no per-photo defocus/focus level can be
inferred reliably — see the stepped-ramp caveat above). `export_all(dest_zip)`
bundles the config JSON + all photos into a .zip and `import_all(src_zip)` restores it (validates
the JSON + basename-only photo extraction against zip-slip; re-applies settings live). Both are in
the Settings panel ("Exporter réglages + photos" / "Importer une sauvegarde") — import closes the
panel afterwards so its now-stale fields can't clobber the freshly-imported config on OK. User
settings are a
registry `_USER_SETTINGS` (JSON key → module global → cast → validator); `_apply_settings_config()`
runs at the **bottom of the module** to override globals (`GCODE_DIR`, `RAPID_FEED_MM_MIN`,
`TRAVEL_CLEARANCE_MM`, `SPINDLE_SELECT`, nozzle, etc.). Invalid values are warned and the default
kept — mirror this policy for new settings.

**Laser profiles (multi-module).** `lasers = {"<id>": {"name", "settings", "nozzle"}}` + `active_laser`
let the workbench carry a separate calibration per physical laser (e.g. blue 450 nm on T100 + IR
1064 nm on T101). `PER_LASER_KEYS` (laser_tool, s_max, frame_power, the spot-calibration trio,
z_work_mm) + the nozzle are per-laser; everything else in `settings` is machine-global. The active
laser's per-laser values are **mirrored into the top-level `settings`/`nozzle`** so all existing code
reads them unchanged. `set_active_laser`/`add_laser`(clone)/`rename_laser`/`delete_laser` manage them;
`_ensure_lasers` migrates a flat config by seeding a "Bleu 450 nm" profile from current values (lazy —
persisted by `ensure_laser_profiles()`, called from the Settings panel). `save_settings`/`save_nozzle`
also mirror the per-laser subset into the active profile. **Per-laser DATA** (`_is_per_laser_data_key`):
the `nuancier`, `burn_widths` and every `presets_*` block are also stored per profile — a blue 450 nm
and an IR 1064 nm don't share grays, burn widths or material power/feed. They stay mirrored at top-level
(the read path: `load_shades`/`load_presets`/`load_burn_widths` are unchanged); `_ensure_lasers` migrates
them into the active profile (incl. a scaffold config where only settings/nozzle were per-laser),
`set_active_laser`/`delete_laser` swap them, and `save_shades`/`save_preset`/`delete_preset`/
`save_burn_widths` call `_mirror_data_to_active_laser`. A new (cloned) laser starts with EMPTY
nuancier/presets/widths. The Settings panel has a "Laser actif" section (combo + clone/rename/delete)
that re-applies + reloads fields on switch.

### Vector label font

`text_to_edges` / `_char_to_edges` / `_FONT_GLYPHS`: a tiny 7-segment font (digits `0-9`, `S`, `F`,
plus `.` and `-`) so labels ("S400", "8.25") need no external font file. Extend `_FONT_GLYPHS` (or the
`.` special-case) if a new glyph is needed.

### Single-line (monoline) text font

Distinct from the 7-segment label font: full **single-stroke** vector fonts for engraving text as
proper "stick" letters (one stroke per branch, like a pen plotter) — the right tool when the medial
axis can't help (holed letters). Several fonts are available (registry `HERSHEY_FONTS` in
`laser_core.py`, key → display label), each a sibling data module `hershey_font[_clé].py`
(`GLYPHES[char] = (adv, [strokes])` in font units, baseline y=0, `CAP_HEIGHT` ≈ 662) generated from
a public-domain **Hershey** SVG font (keep the credit in each module's docstring) — `hershey_font.py`
(no suffix) is the historic default, "Hershey Sans 1-stroke" ("sans"); `hershey_font_script.py` adds
"Hershey Script 1-stroke" ("script", cursive). Only genuinely single-stroke Hershey variants belong
here — most "Med"/"Bold"/"Serif" Hershey variants actually draw each stroke TWICE (duplex/outline,
for a bolder plotted look) and defeat the point of this mode; check a reference glyph's path for a
low, non-doubled stroke count before adding one. `_hershey_module(font)` resolves a registry key to
its data module (silent fallback to "sans" on an unknown key or import failure). Core:
`single_line_text_to_edges(text, height, char_spacing, line_spacing, font="sans")` (height = cap
height) and `create_single_line_text_object(...)`; the **Texte (trait simple)** mode
(`TaskPanelText`) creates a `Part::Feature` wire in the tree to engrave with **Marquage** (reuses
styles/curved/presets). To add a font, generate a new `hershey_font_<clé>.py` sibling module from
the source SVG font (same structure — don't hand-edit) and register it in `HERSHEY_FONTS`; to add
glyphs to an existing font, regenerate its module rather than hand-editing. Known pre-existing gap in
the shipped `hershey_font.py`: a handful of glyphs (ç, Ç, ß, £, ı, İ, æ, Æ…) are present in `GLYPHES`
but with an empty stroke list — the original generator dropped curve-only glyphs instead of keeping
their parseable subpaths — so they render as invisible blanks; not yet fixed.

### Photo engraving & nuancier-driven tone (July 2026)

- Photo mode has 5 tramages: FS dots, variable-duration dots, **calibrated lines**
  (`generate_gcode_photo_lines`: per-pixel S via the measured nuancier curve), **dither lines**
  (`generate_gcode_photo_dither_lines`: FS dither, fixed-S on/off per pixel), **Z dots**
  (`generate_gcode_photo_zdots`: dot DIAMETER renders darkness via per-dot Z, Z moves between dots).
  Shared serpentine emitter `_emit_raster_rows`. Gamma tone control lives in the panel (`spn_gamma`,
  applied in `_build_rows`). `generate_gcode_photo_sampler` = comparison strip of all tramages.
- Nuancier interpolation: `darkness_fluence_curve(material)` (defocused tones only, isotonic/PAVA
  smoothing), `fluence_for_darkness`, `feed_for_custom_shade` — used by Marquage's "ton sur mesure"
  and the calibrated photo modes. Marquage also has style `"degrade"` (linear defocus along a
  direction, `deg_angle`/`deg_z_min`/`deg_z_max` in style_params).
- **MACHINE CONSTRAINT (critical): never emit a G4 dwell with beam on.** The user's HAL scales laser
  power by real/requested velocity → at standstill power is forced to 0, so G4-pulse dots engrave
  NOTHING. All dot-like marks must be micro-strokes (short G1 whose feed reproduces the exposure
  time) — see the dot emission in `generate_gcode_halftone`/`_emit_dots`/zdots. The Marquage
  "pointillé" style still uses G4 dwells (known gap; convert the same way if the user needs it).

### Aperçu photo (rendu du résultat gravé) (July 2026)

The **reverse** of photo mode: paint what the engraving will look like (a "Aperçu photo" button on
Filled/Marquage/Combined). Lives entirely in `task_panels.py` (QPainter is Qt): each burn is drawn as
a thick stroke at its **burn width** (`burn_width_defocus_scaled`, else the optical spot) and a
**tone**. Tone is the **measured nuancier darkness first** (`_tone_measured` → `core.darkness_at`:
shades grouped by measured defocus level, nearest level to the requested defocus, then the same
bilinear S-linear/F-log interpolation as burn widths via the generalized
`_bilinear_burn(..., key="darkness")`, clamped to the measured grid; the material comes from the
panel's own "Nuancier matériau" combo), with the theoretical `_tone_burn` (areal fluence
`P/(width·v)`, saturating `1-exp(-3·f)`) as **fallback** when the material has no usable shade.
An earlier prototype used peak irradiance `P/(spot²·v)`, but it penalised defocus far too hard — a real
MDF burn at S865 F600 defocused 36 mm comes out **dark, not pale** — so the fallback was **recalibrated
on a real engraving** to areal fluence. The fallback still badly overestimates LIGHT tones (MDF S400
F2000: 5% measured vs ~55% predicted — the "light fill renders black" bug), which is why measured data
wins whenever it exists. Strokes are composited with `CompositionMode_Multiply`
on a wood background so overlaps deepen. `_render_engraving_photo(strokes)` → QImage, `_show_image_dialog` shows it + PNG save.
`_strokes_from_operation(op)` maps a combined-job operation dict (filled/curved/flat/curved_cut) to
strokes, so `TaskPanelCombined` renders the whole job at once; testgrid/unknown types are skipped
(no material context there either → fallback tone). Per-panel previews build strokes directly (no
`_build_combined_operation`, to avoid its save/Job side effects). Hachures is a geometry mode
(no power/feed) → no preview.

## Hardware context

Default profile is the **LT-80W-AA-PRO** diode module with the square shroud removed (so it can
follow curved surfaces) — the anti-collision cone model (`NOZZLE_*`) and the focus table
(`FOCUS_TABLE`) come from that module and are overridable via Preferences / config. See README.md
"Matériel testé" / "Adapter à un autre laser" before changing collision or focus constants.

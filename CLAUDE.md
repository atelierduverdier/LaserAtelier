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
  AND cutting tabs), the AXE MÉDIAN / centerline extractor (`centerline_edges(edges)` → skeleton
  edges + stroke width: **Voronoi-first** (`_centerline_voronoi`) — rebuild the filled face(s) from
  the contour (`Part.makeFace` Bullseye, holes included), run FreeCAD's native `Path.Voronoi` (CAM
  module) whose diagram of the boundary segments IS the exact medial axis, keep the interior PRIMARY
  edges via the FreeCAD Vcarve colour recipe (`colorColinear`/`colorExterior`/`colorTwins`), then
  prune short leaf branches (`_voronoi_polylines`) to keep only the SPINE — the fans to convex
  vertices (wanted by a V-bit, not by the laser's fat point) are removed. Vector, resolution-
  independent, holes handled; `import Path` is lazy & guarded with graceful **fallback to the old
  raster method** `_centerline_raster` (even-odd rasterise → Zhang-Suen thinning → trace → spur
  prune → merge; numpy) if the CAM module is absent. Marquage's "Graver l'axe médian" checkbox uses
  it to engrave a filled glyph's skeleton with the defocused fat spot instead of contour+fill), fluence (`line_fluence`/`power_for_line_fluence`), the measured-tones nuancier
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
    for any new shape-based panel. In the 4 G-code shape panels (filled/curved/flat/curved_cut),
    **OK only saves settings and closes**; generation goes through the dedicated
    "Générer et sauvegarder le G-code…" button (`_on_save_gcode`, which re-saves then generates).
    `_build_combined_operation` also saves on success, so the combined-job path feeds the
    per-shape settings and the tree Job too.
  - `_PresetController(form, parent, category, fields_getter)` — preset selector block backed by
    `core.factory_presets` (★, non-deletable) + user presets.
  - `_make_fluence_widgets` / `_fluence_advice` — "Puissance vs défocus" section (power compensation
    from a measured reference, model F ∝ P/(d·v)). The reference fields are a **calibration**, not job
    params: read-only by default (an "Modifier la référence" checkbox unlocks them) so tweaking the
    job can't clobber them; `setValue` (restore/presets) still works while locked.
  - `_make_shade_picker(form, on_apply)` — "Nuancier matériau" block (apply a measured gray tone).
  - `_make_photo_section(form, cle_getter, titre)` — reusable "Photo du résultat" section: a
    dropdown of ALL photos for the current `cle_getter()` key (e.g. `"testgrid:MDF"`, `"defocus"`) +
    a clickable thumbnail (→ `_show_image_dialog`) + add/delete buttons. Returns `{"reload": fn}`
    (accepts an optional select index) to call at end of `__init__` and on material change. Backed
    by core photo helpers (see persistence).
  - **Test/calibration panel convention (①②③)**: every burn-and-measure mode reads top-to-bottom
    as **① Graver** (burn params; Test grid adds an "Objectif" recommended-recipe combo via
    `self._recipes`) → **② Entrer les mesures** (data typed INLINE — no separate dialog, no trip to
    Preferences; writes to `save_burn_widths`/`save_shades`/`save_settings` or computes a value to
    copy out for kerf/offset) → **③ Photo du résultat** (`_make_photo_section`). Nuancier is the
    shared ledger (no burn step → no ①). Follow this for any new test mode.
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
- **`commands.py`**: one `*Command` class per mode (`GetResources`/`IsActive`/`Activated`) that opens
  the matching task panel via `_show(panel)` (closes any active task dialog first — FreeCAD refuses a
  second one otherwise); `register_commands()` registers them all.
- **`InitGui.py`**: the `Workbench` class — toolbar/menu order (`command_list`), lazy imports in
  `Initialize()`. Runs at FreeCAD startup.

**Adding a mode** touches all four: a generator in `laser_core`, a panel in `task_panels`, a command
in `commands.py` (+ `register_commands`), an entry in `InitGui.py`'s `command_list` (grouped by theme
with `"Separator"` tokens), and an SVG in `resources/icons/` (64×64, orange `#ff8a00` + slate
`#2f3540` house style; `sect_*.svg` are the small section pictos reused across panels). Every mode
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

### Defocus model (used by filled-engraving, defocus fill, calibration)

A linear divergence cone calibrated from **two real measurements** (never guessed):
`defocus_divergence_half_angle(d_focus, d_calib, z_calib)` → `spot_diameter_at_defocus(z, …)` →
`defocus_for_fill_spacing(spacing, …)`. The **fill is inset by the spot radius** so the burn stays
inside the outline (`fill_inset` in `build_test_grid_cells` / `build_filled_engraving_edges`,
via square inset or `Part.Face.makeOffset2D(-r)` with graceful fallback for thin strokes). When a
contour is drawn, the filled-engraving panel (`TaskPanelFilledEngraving._fill_inset`) reduces that
inset by the **contour's burn radius** so the fill deliberately tucks *under* the contour (re-burned
at focus on top) — closing the pale liseré left at the edge, most visible at high defocus where the
optical spot over-estimates the real burn width. Outward overspill is bounded by the contour radius so
it stays hidden; a wider contour closes more of the gap.

The **measured** burn width (which drives fill spacing/inset, not the optical spot) is
`burn_width_defocus_scaled(power, defocus)`. The calibration plank (`generate_gcode_material_board`,
section 2) burns the defocus test at **several levels** — `DEFOCUS_LEVELS_MM` (≈15/36/50 mm), one
column each — and `burn_width_defocus_scaled` **interpolates** the width between the two bracketing
levels (linear in defocus, linear in S within a level); outside the measured range, or with a single
level, it falls back to the old proportional-to-optical-spot extrapolation. Measurements are entered
per level in the "Saisir les mesures de la planche…" dialog (one defocus column per level, stored with
each point's `z_offset`; old single-level data maps to the nearest level). This replaces the earlier
single-point average that over-estimated the burn at a working defocus (e.g. 36 mm) far from the one
measured point (~15 mm) — the root cause of the liseré that v1.11.2 could only mask with the contour.

### Persistence & user settings

Single JSON file `laser_atelier_config.json` in FreeCAD's user app-data dir
(`load_config`/`save_config`). Holds: material `presets_*`, `nozzle` profile, per-mode pre/post
G-code, a `settings` block, laser profiles (`lasers` + `active_laser`), and a `photos` block
(key → LIST of relative filenames; an old single-string value is migrated on read). **Result
photos** (several per test/calibration key) live in a `photos_resultats/` subdir of the **workbench
dir** (`_WORKBENCH_DIR`, next to the code so they survive deleting the original; gitignored;
migrated once from the old `app-data/laser_atelier_photos`); core helpers `photos_dir`/
`result_photos`/`add_result_photo`/`delete_result_photo` (the last takes an optional filename; None
clears all) copy/list/forget them (no Qt — the panel paints the thumbnail). `export_all(dest_zip)`
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

Distinct from the 7-segment label font: a full **single-stroke** vector font for engraving text as
proper "stick" letters (one stroke per branch, like a pen plotter) — the right tool when the medial
axis can't help (holed letters). Data lives in **`hershey_font.py`** (`GLYPHES[char] = (adv, [strokes])`
in font units, baseline y=0, `CAP_HEIGHT` ≈ 662), a generated blob of the public-domain **Hershey Sans
1-stroke** font (216 glyphs incl. lowercase + French accents; keep the Hershey credit). Core:
`single_line_text_to_edges(text, height, char_spacing, line_spacing)` (height = cap height) and
`create_single_line_text_object(...)`; the **Texte (trait simple)** mode (`TaskPanelText`) creates a
`Part::Feature` wire in the tree to engrave with **Marquage** (reuses styles/curved/presets). To add
glyphs, regenerate `hershey_font.py` from the source SVG font rather than hand-editing.

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
**tone** (`_tone_burn` = areal fluence `P/(width·v)` = energy per burned area, saturating `1-exp(-3·f)`).
An earlier prototype used peak irradiance `P/(spot²·v)`, but it penalised defocus far too hard — a real
MDF burn at S865 F600 defocused 36 mm comes out **dark, not pale** — so the model was **recalibrated on
a real engraving** to areal fluence (fills read dark once above the char threshold; only genuinely
under-powered/over-defocused settings stay pale). Strokes are composited with `CompositionMode_Multiply`
on a wood background so overlaps deepen. `_render_engraving_photo(strokes)` → QImage, `_show_image_dialog` shows it + PNG save.
`_strokes_from_operation(op)` maps a combined-job operation dict (filled/curved/flat/curved_cut) to
strokes, so `TaskPanelCombined` renders the whole job at once; testgrid/unknown types are skipped.
Per-panel previews build strokes directly (no `_build_combined_operation`, to avoid its save/Job side
effects). Theoretical render — accuracy scales with the burn-width plank; nuancier-driven tone is a
possible refinement (not wired yet). Hachures is a geometry mode (no power/feed) → no preview.

## Hardware context

Default profile is the **LT-80W-AA-PRO** diode module with the square shroud removed (so it can
follow curved surfaces) — the anti-collision cone model (`NOZZLE_*`) and the focus table
(`FOCUS_TABLE`) come from that module and are overridable via Preferences / config. See README.md
"Matériel testé" / "Adapter à un autre laser" before changing collision or focus constants.

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

Four modules, cleanly layered — keep the layering:

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
    (fall back to text if the SVG picto fails, `_icon_pixmap` returns None).
  - `_WrapLabel` — paragraph label: word-wrap on, **collapses manual `\n` into spaces** (mixing both
    caused stair-stepped text). Never put an enumeration in ONE `_WrapLabel` — use
    `_bullet_list(form, items)` (one label per item) instead.
  - `_intro(form, resume, details)` — short always-visible summary + details folded behind an
    "En savoir plus" toggle. `_diagram(form, "diag_*.svg")` — explanatory schematics rows.
  - `_set_row_visible(form, widget, bool)` — hides label+field together (plain `setVisible` leaves
    orphan labels in a QFormLayout).
  - Last-session persistence: each panel builds `self._last_fields = {key: widget}`, calls
    `_restore_last_values(key, fields)` at end of `__init__` and `_save_last_values` in `accept()`
    (`_widget_get/_widget_set` handle combo/checkbox/spin/lineedit). Priority: last values >
    Preferences defaults.
  - `_PresetController(form, parent, category, fields_getter)` — preset selector block backed by
    `core.factory_presets` (★, non-deletable) + user presets.
  - `_make_fluence_widgets` / `_fluence_advice` — "Puissance vs défocus" section (power compensation
    from a measured reference, model F ∝ P/(d·v)).
  - `_make_shade_picker(form, on_apply)` — "Nuancier matériau" block (apply a measured gray tone).
  - **Job combiné**: operations are NOT added via bespoke mini-dialogs anymore. Each combinable mode
    (Flat cut, Curved cut, Curved marking, Test grid) has a `_build_combined_operation()` returning
    `{type,label,params}` (params = the exact kwargs its own generator uses, full-featured) and a
    `_combined_add_button(form, self._on_add_to_combined)` that appends to the module-level list
    `_COMBINED_OPS` (in-memory: params carry Part edges/probe, not JSON-serializable). `TaskPanelCombined`
    reads `_COMBINED_OPS` (its `self.operations` IS that list), reorders/removes/clears, and generates.
    Reuse this pattern for any new combinable mode instead of a simplified duplicate dialog.
- **`commands.py`**: one `*Command` class per mode (`GetResources`/`IsActive`/`Activated`) that opens
  the matching task panel via `_show(panel)` (closes any active task dialog first — FreeCAD refuses a
  second one otherwise); `register_commands()` registers them all.
- **`InitGui.py`**: the `Workbench` class — toolbar/menu order (`command_list`), lazy imports in
  `Initialize()`. Runs at FreeCAD startup.

**Adding a mode** touches all four: a generator in `laser_core`, a panel in `task_panels`, a command
in `commands.py` (+ `register_commands`), an entry in `InitGui.py`'s `command_list` (grouped by theme
with `"Separator"` tokens), and an SVG in `resources/icons/` (64×64, orange `#ff8a00` + slate
`#2f3540` house style; `sect_*.svg` are the small section pictos reused across panels).

### G-code generation contract

Generators are `generate_gcode_*(...)` in `laser_core.py`, each returning a **sanitized G-code
string or `None`** (None = empty geometry). Shared conventions:

- **LinuxCNC RS274 dialect**: laser is spindle `$1` (`SPINDLE_SELECT`); header is
  `G21/G90/G94/G43 H<n>` (`cmd_tool_comp()` — a function, not a constant, so it follows the
  `LASER_TOOL` preference, default 100) then `M5 $1`; arm once with `CMD_ARM` (`M3` at zero power +
  dwell), power per segment via `S…` (`CMD_BEAM_ON/OFF`), disarm `M5`, end `M2`. Power fields are
  scaled 0..`S_MAX` (preference `s_max`, default 1000 — panels use `setRange(0, core.S_MAX)`, never
  a hard-coded 1000). **Machine prerequisite:** the operator must have run `T<n> M6` in the LinuxCNC
  session (the `G43 H<n>` applies the laser tool's X/Y offsets + probed Z).
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
via square inset or `Part.Face.makeOffset2D(-r)` with graceful fallback for thin strokes).

### Persistence & user settings

Single JSON file `laser_atelier_config.json` in FreeCAD's user app-data dir
(`load_config`/`save_config`). Holds: material `presets_*`, `nozzle` profile, per-mode pre/post
G-code, a `settings` block, and laser profiles (`lasers` + `active_laser`). User settings are a
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
also mirror the per-laser subset into the active profile. **Still global (next step):** the nuancier
(`shades`) and material `presets_*` are not yet per-laser. The Settings panel has a "Laser actif"
section (combo + clone/rename/delete) that re-applies + reloads fields on switch.

### Vector label font

`text_to_edges` / `_char_to_edges` / `_FONT_GLYPHS`: a tiny 7-segment font (digits `0-9`, `S`, `F`,
plus `.` and `-`) so labels ("S400", "8.25") need no external font file. Extend `_FONT_GLYPHS` (or the
`.` special-case) if a new glyph is needed.

## Hardware context

Default profile is the **LT-80W-AA-PRO** diode module with the square shroud removed (so it can
follow curved surfaces) — the anti-collision cone model (`NOZZLE_*`) and the focus table
(`FOCUS_TABLE`) come from that module and are overridable via Preferences / config. See README.md
"Matériel testé" / "Adapter à un autre laser" before changing collision or focus constants.

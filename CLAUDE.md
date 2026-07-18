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
- **`task_panels.py` needs PySide6 + a running FreeCAD** — verify UI changes by the user restarting
  FreeCAD (or reloading the workbench). It cannot be exercised headless.
- The repo lives in the user's `Mod` dir; a **FreeCAD restart** picks up changes. Commit + push are
  routine for this personal project.

## Architecture

Four modules, cleanly layered — keep the layering:

- **`laser_core.py`** (~3k lines): ALL geometry + G-code logic. **No Qt.** This is where generators,
  the defocus model, the vector font, config persistence, and geometry helpers live. Organized into
  banner-commented sections, one per mode. This is the layer you unit-test headless.
- **`task_panels.py`** (~3.7k lines): one `TaskPanel*` class per mode (PySide6/Qt). Builds the form,
  reads widgets, calls `core.*` generators, writes the file via `_write_gcode_with_dialog`. Pure UI;
  no geometry math beyond calling core. Shared UI helpers: `_panel_header(form, icon, title)` (mode
  banner) and `_section(form, title, icon)` (bold section header + rule) structure the dense panels —
  both fall back to text if the SVG picto fails to render (`_icon_pixmap` returns None). Preset
  save/load (material presets) reuses `core.load_presets/save_preset/delete_preset` per category.
- **`commands.py`**: one `*Command` class per mode (`GetResources`/`IsActive`/`Activated`) that opens
  the matching task panel; `register_commands()` registers them all.
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
  `G21/G90/G94/G43 H100` (`CMD_TOOL_COMP`, tool-length comp for T100) then `M5 $1`; arm once with
  `CMD_ARM` (`M3` at zero power + dwell), power per segment via `S…` (`CMD_BEAM_ON/OFF`), disarm
  `M5`, end `M2`. **Machine prerequisite:** the operator must have run `T100 M6` in the LinuxCNC
  session (the `G43 H100` applies the laser tool's X/Y offsets + probed Z).
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
G-code, and a `settings` block. User settings are a registry `_USER_SETTINGS` (JSON key → module
global → cast → validator); `_apply_settings_config()` runs at the **bottom of the module** to
override globals (`GCODE_DIR`, `RAPID_FEED_MM_MIN`, `TRAVEL_CLEARANCE_MM`, `SPINDLE_SELECT`, nozzle,
etc.). Invalid values are warned and the default kept — mirror this policy for new settings.

### Vector label font

`text_to_edges` / `_char_to_edges` / `_FONT_GLYPHS`: a tiny 7-segment font (digits `0-9`, `S`, `F`,
plus `.` and `-`) so labels ("S400", "8.25") need no external font file. Extend `_FONT_GLYPHS` (or the
`.` special-case) if a new glyph is needed.

## Hardware context

Default profile is the **LT-80W-AA-PRO** diode module with the square shroud removed (so it can
follow curved surfaces) — the anti-collision cone model (`NOZZLE_*`) and the focus table
(`FOCUS_TABLE`) come from that module and are overridable via Preferences / config. See README.md
"Matériel testé" / "Adapter à un autre laser" before changing collision or focus constants.

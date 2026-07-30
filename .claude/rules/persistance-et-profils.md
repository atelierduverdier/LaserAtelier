---
paths:
  - "laser_core.py"
---

# Persistence, user settings, laser profiles

## The single config file

One JSON file `laser_atelier_config.json` in FreeCAD's user app-data dir
(`load_config`/`save_config`). **See CLAUDE.md rule 3: never write to it from a test or an
experiment.** It holds:

- material `presets_*`
- the `nozzle` profile
- per-mode pre/post G-code
- a `settings` block
- laser profiles (`lasers` + `active_laser`)
- the `nuancier` (judged tones) and `burn_widths` (calliper-measured line widths)
- a `sections` block (open/closed state of each panel section, keyed by title)
- a `photos` block: key → **LIST** of `{"file": relative filename, "description": free text}`. An old
  single-string value, or a bare list of filenames, is migrated on read by `_photo_list`.

## Result photos

Several per test/calibration key, living in a `photos_resultats/` subdir of the **workbench dir**
(`_WORKBENCH_DIR`, next to the code so they survive deleting the original; gitignored; migrated once
from the old `app-data/laser_atelier_photos`).

Core helpers — no Qt, the panel paints the thumbnail: `photos_dir` / `result_photos` /
`add_result_photo` / `set_photo_description` / `delete_result_photo` (the last takes an optional
filename; None clears all).

The **description** field exists because no per-photo defocus/focus level can be inferred reliably
from panel state — the user types what regime the board was burned at, and that is often the only
record of it.

## Export / import

`export_all(dest_zip)` bundles the config JSON + all photos into a .zip; `import_all(src_zip)`
restores it (validates the JSON, and extracts photos **basename-only** against zip-slip; re-applies
settings live). Both are in the Settings panel ("Exporter réglages + photos" / "Importer une
sauvegarde") — **import closes the panel afterwards** so its now-stale fields can't clobber the
freshly-imported config on OK.

## User settings registry

A registry `_USER_SETTINGS`: JSON key → module global → cast → validator. `_apply_settings_config()`
runs at the **bottom of the module** to override globals (`GCODE_DIR`, `RAPID_FEED_MM_MIN`,
`TRAVEL_CLEARANCE_MM`, `SPINDLE_SELECT`, `Z_WORK_MM`, nozzle, etc.).

**Invalid values are warned about and the default kept** — mirror that policy for any new setting.

Machine constants live here rather than in panels (`Z_WORK_MM`, `TRANSIT_MARGIN_MM`,
`SPOT_FOCUS_MM`…): panels read them instead of exposing their own Z fields. Cutting modes keep a
per-job Z because nozzle height is thickness-dependent safety.

## Laser profiles (multi-module)

`lasers = {"<id>": {"name", "settings", "nozzle"}}` + `active_laser` let the workbench carry a
separate calibration per physical laser (e.g. blue 450 nm on T100 + IR 1064 nm on T101).

`PER_LASER_KEYS` (laser_tool, s_max, frame_power, the spot-calibration trio, z_work_mm) + the nozzle
are **per-laser**; everything else in `settings` is machine-global. The active laser's per-laser values
are **mirrored into the top-level `settings`/`nozzle`** so all existing code reads them unchanged.

`set_active_laser` / `add_laser` (clone) / `rename_laser` / `delete_laser` manage them.
`_ensure_lasers` migrates a flat config by seeding a "Bleu 450 nm" profile from current values (lazy —
persisted by `ensure_laser_profiles()`, called from the Settings panel). `save_settings`/`save_nozzle`
also mirror the per-laser subset into the active profile.

### Per-laser DATA

`_is_per_laser_data_key`: the `nuancier`, `burn_widths` and every `presets_*` block are **also stored
per profile** — a blue 450 nm and an IR 1064 nm don't share greys, burn widths or material
power/feed. They stay mirrored at top-level (so the read path `load_shades`/`load_presets`/
`load_burn_widths` is unchanged); `_ensure_lasers` migrates them into the active profile (including a
scaffold config where only settings/nozzle were per-laser), `set_active_laser`/`delete_laser` swap
them, and `save_shades`/`save_preset`/`delete_preset`/`save_burn_widths` call
`_mirror_data_to_active_laser`.

**A new (cloned) laser starts with an EMPTY nuancier/presets/widths.** The Settings panel has a "Laser
actif" section (combo + clone/rename/delete) that re-applies and reloads fields on switch.

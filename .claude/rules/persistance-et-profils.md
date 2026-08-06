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

## Rectified boards — a separate folder, and the laser in the filename

`PLANCHES_DIR` (setting `planches_dir`, default `~/Planches-LaserAtelier`) holds the rectified
measurement images, **not** the source-photo folder. A rectified board is not a photo, it is an
instrument at an exact, ruler-verified scale; kept beside the raw `IMG_*.JPG` it gets lost, and
each one is 55 MB.

`nom_planche_redressee(planche, horodatage, suffixe, laser=None)` builds
`<laser>_<planche>_<date>_redresse`, the laser coming from `active_laser_name()` through
`slug_fichier` (accents dropped, no separator can survive — a `/` in a profile name would write
somewhere else entirely). **The laser belongs in the name**: a burn width only means something for
the module that produced it — two diodes give two different tables — and conversely someone with
the *same* module can reuse these measurements without an hour at the bench. Without the name on
the file, that reuse requires remembering, which means it won't happen.

Each rectification writes four files there: the lossless PNG (measuring), a `.json` **fiche**
(mm size, px/mm, ruler verification, laser), a ~0.5 MB JPEG preview, and the `_reperes.jpg`
control. The fiche is written **unconditionally**, not only when the caller passes `--json`:
without it an image has no scale, and the only way back is to redo the whole rectification. Only
the preview is copied into `photos_resultats/` — `add_result_photo` copies, and copying the 55 MB
PNG per run piled up 290 MB in one morning (2026-08-01).

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

### The three GUESSED settings, and why they are read from the machine (v2.99.34)

`RAPID_FEED_MM_MIN`, `Z_MAX_FEED_MM_MIN` and `ACCEL_MM_S2` were the only settings neither measured
on wood nor chosen — they were **supposed**, with conservative factory values nothing flagged as
such. `limites_depuis_ini(chemin)` reads them from the machine's own LinuxCNC `.ini`
(`chemins_ini_probables()` + the remembered `chemin_ini_linuxcnc`); the Preferences button fills the
three fields and **says which section and key each number came from**. On the workshop's PrintNC it
yields 8000 / 3000 / 600 — exactly what Christophe had typed by hand, which is the proof the reader
is worth having.

**The two are not the same size of problem, and the measurement says so:**

- `RAPID_FEED` is nearly cosmetic. Measured over the 70 real `.ngc` files, 6000 against 8000 moves
  the announced duration by **+0.4 %** (+2 % worst case): at 600 mm/s² a rapid of a few millimetres
  never reaches its top speed, so the acceleration governs. Don't chase it.
- `Z_MAX_FEED` is **not** an estimate — `pente_z_max` reads it, so it sets the Z slope the spindle
  allows. At 1500 instead of 3000 the slope halves and `longueur_mini_fuseau` **doubles** (5.3 mm
  instead of 2.7 at F200): half as many motifs across the same image. Lost engraving detail, not a
  wrong number on screen.

**Do NOT raise the shipped default to match a real machine.** Too low only costs detail; too high
lets the generator authorise a slope the axis cannot follow, LinuxCNC then slows the *whole* move so
Z can keep up, the dwell time changes and therefore the darkness — silently, the exact failure mode
`pente_z_max`'s docstring exists to prevent. Writing Christophe's machine into the code would swap
one guess for another and hand that trap to anyone with a slow Z.

Parsing traps, all covered by `tests/test_limites_ini.py`: velocities are **units per SECOND**
(hence ×60), `[TRAJ] LINEAR_UNITS` may be `inch`, `[AXIS_*]` beats `[JOINT_*]` (a gantry has more
joints than axes — the PrintNC has 4 for 3), the rapid takes the **most constraining** of X/Y/TRAJ
rather than the flattering maximum, and an unreadable file replaces **nothing** — a fallback default
would silently overwrite a correct value. Written by hand rather than with `configparser`, which
rejects or collapses the duplicate keys a LinuxCNC `.ini` legitimately carries.

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

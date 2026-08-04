# CLAUDE.md

Guidance for Claude Code working in this repository.

**This file holds only what must be true in EVERY session.** Everything else lives in
`.claude/rules/`, scoped by file path so it loads when you actually touch the matching code —
see [Topic rules](#topic-rules) at the bottom. This file and `.claude/rules/*.md` are the only
English exception to the French convention below.

## What this is

A **FreeCAD workbench** (FreeCAD 1.1) turning 2D/3D geometry into LinuxCNC G-code for a
diode-laser head on a CNC: marking, filled engraving, photo halftones, multi-pass cutting,
test grids, calibration boards. The repository **is** the workbench directory:

```bash
git clone <repo> ~/.local/share/FreeCAD/<version>/Mod/LaserAtelier   # e.g. v1-1
```

No build system, no linter, no CI. FreeCAD loads the `.py` files at startup; a **restart**
picks up changes. The version is `VERSION` in `laser_core.py` — read it there rather than
trusting a number written here; this line went **44 releases** out of date before anyone looked.

## Non-negotiables

### 1. Everything is in French

Code comments, docstrings, UI strings, tooltips, generated G-code comments, **and git commit
messages**. Keep new code in French to match.

### 2. The engraved piece outranks every test you can write

The costliest defects here were found by the user looking at wood, or *listening* to the head
move — never by a test, never by re-reading code. A test only checks what someone already
thought to doubt. Concretely: a nuancier board exposed tones judged identical that render
nothing alike, plus one that engraved nothing at all; a gradient coming out solid black exposed
a photo chain wrong end to end — and the mire meant to validate it carried the *same* fault, so
it could not possibly have caught it; four strips at identical energy but four speeds proved
darkness also depends on dwell time, which no formula fix could repair; and twice, the head's
motion alone betrayed wasted travel in the dot halftones (the second time a full month after
the "fix").

Treat "this patch is darker than that one although it should be lighter" as a measurement that
settles the question — because it is one, and it outranks your reasoning. When a hypothesis and
the wood disagree, the wood is right. Ask for a small control board rather than theorise: three
wrong mechanisms were proposed in one afternoon before an engraving settled it.

### 3. NEVER write to the live config

`laser_atelier_config.json` (FreeCAD's user app-data dir) holds **calliper measurements taken on
real wood** — hours of bench time that no computation can reproduce. To test anything that
writes, copy the file and repoint `core.CONFIG_FILE` at the copy (that is what
`tests/harness.py` does). After touching the harness, verify the live config's md5 and mtime are
unchanged by a full run.

### 4. NEVER emit a `G4` dwell with the beam on

The user's HAL scales laser power by real/requested velocity → **at standstill power is forced to
0**, so a G4-pulse dot engraves NOTHING and the job comes out silently blank. Every dot-like mark
is a **micro-stroke**: a short `G1` whose feed reproduces the exposure time. (The Marquage
"pointillé" style was once listed here as a remaining gap — verified CLOSED on 2026-08-02: all
three call sites go through `dot_micro_stroke`, and a generated file shows zero beam-on `G4`.)

### 5. Never test novel OCC/Qt call patterns in the user's live FreeCAD session

A per-wire `makeOffset2D` experiment segfaulted the whole GUI and lost unsaved work. Run risky
probes with the AppImage python on a copy in the scratchpad.

### 6. Commits

Commit + push directly to `main` (personal repo), no `Co-Authored-By` trailer, message in French.
**Check `git status` first** — concurrent Claude sessions share this working directory, so stage
your own files explicitly rather than `git add -A`.

## Versioning ritual

Single source of truth: `VERSION` in `laser_core.py` — shown in every panel banner and stamped as
the first line of every written G-code. Bump it **together, in ONE commit**, with:

| File | What |
|---|---|
| `laser_core.py` | `VERSION = "x.y.z"` |
| `package.xml` | `<version>` **and** `<date>` |
| `docs/index.html` | hero badge |
| `README.md` | version line under the logo |
| `docs/manuel.html` | **3 occurrences** |
| `docs/Manuel-LaserAtelier.pdf` | regenerate: `weasyprint docs/manuel.html docs/Manuel-LaserAtelier.pdf` |

Tag releases `v<version>` on `main`. **A purely documentary change does NOT bump the version.**

## Verifying changes

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('laser_core.py','task_panels.py','commands.py','InitGui.py','svg_import.py')]"
```

That syntax check is the only automated gate — run it after every edit. Then the test suite:

```bash
python3 tests/lancer.py
```

Run the suite with the **system** python; the runner only delegates, rediscovering FreeCAD's own
interpreter under `/tmp/.mount_FreeCA*` (that mount path **changes every time FreeCAD is
relaunched**, and a stale path looks exactly like a broken environment). Final visual validation
is always the user restarting FreeCAD.

## Architecture

Seven modules, cleanly layered — keep the layering:

| Module | Lines | Role |
|---|---|---|
| `laser_core.py` | ~13 000 | ALL geometry + G-code logic. **No Qt.** Generators, defocus model, fonts, persistence, `_USER_SETTINGS`. The layer you unit-test headless. |
| `task_panels.py` | ~18 600 | One `TaskPanel*` per mode (PySide6). Pure UI: builds the form, reads widgets, calls `core.*`. No geometry math. |
| `laser_jobs.py` | ~300 | Tree "Job" objects — bookmarks, not a second source of truth. |
| `svg_import.py` | ~730 | Standalone SVG→geometry parser, no Draft/DXF detour. |
| `calligraphie.py` | ~1 400 | Standalone OTF/TTF → skeleton + local stroke width (numpy/scipy/PIL). No FreeCAD, no Qt. Feeds the Z spindle. |
| `commands.py` | ~530 | One `*Command` per mode + `register_commands()`. |
| `InitGui.py` | ~240 | The `Workbench` class: toolbar/menu order, lazy imports. |

`laser_core.py` is organised into banner-commented sections, one per mode. Keep that shape.

### Adding a mode

Touches five places: a generator in `laser_core.py`, a panel in `task_panels.py`, a command in
`commands.py` (+ `register_commands`), an entry in `InitGui.py`'s `command_list` (grouped by theme
with `"Separator"` tokens), and a 64×64 SVG in `resources/icons/` (orange `#ff8a00` + slate
`#2f3540` house style). A self-contained subsystem may keep its generator-equivalent logic in its
own sibling module instead of `laser_core.py` — `laser_jobs.py`, `svg_import.py` and
`calligraphie.py` are the three such exceptions — but it still touches the same panel/command/`InitGui`/icon points.

Every **mode** icon carries the **chapeau signature** (small bowler hat, bottom-right,
`class="chapeau-verdier"` group — copy it verbatim from any marked icon or from `chapeau.svg`);
keep it out of `sect_*.svg` and `diag_*.svg`. Mode icons are mirrored in `docs/assets/` for the
doc site — sync the copy when an icon changes. **SVG gotcha:** QtSvg renders NOTHING, silently, if
the XML is invalid (e.g. `--` inside a comment) — validate with `xmllint --noout`.

## Hardware context

Default profile is the **LT-80W-AA-PRO** diode module with the square shroud removed (so it can
follow curved surfaces): the anti-collision cone model (`NOZZLE_*`) and the focus table
(`FOCUS_TABLE`) come from that module and are overridable via Preferences / config. Read
README.md's "Matériel testé" / "Adapter à un autre laser" before changing collision or focus
constants.

## Topic rules

Detail lives in `.claude/rules/`, each file scoped with `paths:` frontmatter so it enters context
when you read matching code. Read the relevant one **before** working in that area — they carry
the measured numbers and the traps, not summaries:

| Rule | Loads when you touch | Covers |
|---|---|---|
| `generateurs-gcode.md` | `laser_core.py` | G-code contract, 3 dialects, sanitizer, G64, micro-strokes, chain ordering, stepped ramps, defocus & burn-width model, vector fonts |
| `photo-et-tramages.md` | `laser_core.py`, `task_panels.py` | The 8 tramages, nuancier curve, "darkness ≠ energy alone", similigravure, swelling lines, photo preview |
| `panneaux-ui.md` | `task_panels.py`, `laser_jobs.py` | Shared UI helpers, the ①②③ convention, combined jobs, presets, shade picker, per-object settings, face-building perf |
| `persistance-et-profils.md` | `laser_core.py` | Config JSON schema, `_USER_SETTINGS`, per-laser profiles and per-laser DATA, result photos, export/import |
| `tests-headless.md` | `tests/**` | Harness, stubs, the throwaway-config rule, what `test_panneaux.py` covers |
| `svg-import.md` | `svg_import.py` | Parser layering, flattening tolerance, out-of-scope SVG features |
| `calligraphie.md` | `calligraphie.py` | Skeleton, the chain invariant, which measure judges a stroke, font licences |

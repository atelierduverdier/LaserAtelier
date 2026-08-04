---
paths:
  - "tests/**"
---

# Headless tests

```bash
python3 tests/lancer.py            # everything
python3 tests/lancer.py lignes am  # only names containing these
```

Run it with the **system** python — the runner only delegates. It rediscovers FreeCAD's own
interpreter under `/tmp/.mount_FreeCA*` on every run, because **that mount path changes each time
FreeCAD is relaunched** and a stale path looks exactly like a broken environment. Each test runs in
its **own subprocess**, so a Qt panel that crashes or a global it mutated can't contaminate the
next one.

To run one test by hand (e.g. to see its prints):

```bash
PYTHONPATH=/tmp/.mount_FreeCAxxxxxx/usr/lib:tests:. /tmp/.mount_FreeCAxxxxxx/usr/bin/python tests/test_xxx.py
```

## The harness

Tests start with `from harness import preparer` → `h = preparer()`, then use `h.core` / `h.tp`. The
harness sets Qt offscreen, stubs `FreeCADGui.Selection` (several panels read the 3D selection at
construction and it doesn't exist headless), and — **the rule that matters most here** — redirects
`core.CONFIG_FILE` and `core._WORKBENCH_DIR` to a throwaway **copy**.

**A test must never write to the workshop config.** It holds calliper measurements taken on real
wood, hours of bench time no computation can reproduce. The copy keeps the same data, so tests read
the real nuancier and the real kerf table, but every write goes to the bin. After touching the
harness, verify the live config's **md5 and mtime are unchanged** by a full run.

`preparer(config_reelle=False)` starts from an EMPTY config — for the "no material measured yet"
paths.

Shared helpers in `harness.py`: `texte` (strips HTML from a verdict label — verdicts are written in
HTML, so a test grepping the raw markup misses the moment something gets bolded), `mouvements`,
`trajet_a_vide`, `demi_tours_x`, `hauteurs_z`, `puissances(gcode, gravure_seule=)`, `image_demo`.

**`sans_dialogues()` before any test that CLICKS a button.** `QMessageBox.information` waits for a
human click, and offscreen it simply waits forever — the test freezes with **no output at all**
(prints are still buffered), which looks exactly like an infinite loop in your own code. It returns
the list of `(genre, titre, texte)` the panel would have shown, so a test may also assert on what
was announced.

## Why they live in the repo

These tests lived in `/tmp` until the v2 work started, and vanished when the tmpfs was cleared.
That's why they're in the repo now — a cleanup pass over 20 000 lines without a net is a gamble.

## Stubbing patterns (when a test can't use the harness)

`laser_core.py` alone, with FreeCAD stubbed before importing:

```python
import sys, types
fc = types.ModuleType("FreeCAD")
fc.getUserAppDataDir = lambda: "/tmp/whatever"
fc.Console = types.SimpleNamespace(PrintMessage=lambda m: None, PrintWarning=lambda m: None)
class Vector:
    def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = float(x), float(y), float(z)
fc.Vector = Vector
sys.modules["FreeCAD"] = fc
sys.modules["Part"] = types.ModuleType("Part")
import laser_core as core
```

For functions touching real `Part` geometry (`build_test_grid_cells`, `generate_hatch_edges`,
`build_filled_engraving_edges`, `text_to_edges`), monkeypatch the specific helper
(`core.chain_edges`, `core.generate_hatch_edges`, `core.text_to_edges`) or
`core.generate_gcode_curved` to capture arguments, rather than reimplementing OpenCascade. Assert on
the produced G-code string.

`task_panels.py` CAN be exercised headless (system PySide6 exists outside FreeCAD): stub `FreeCAD`
(Vector also needs `distanceToPoint`/`isEqual`), `FreeCADGui` (`Selection.getSelectionEx` returning
a controllable list — keep it EMPTY when instantiating panels, fake shapes lack `BoundBox`), and
`Part` (`LineSegment(+toShape→edge with discretize(Distance=…))`, `Wire`/`Face`/`Compound` as
identity lambdas), monkeypatch `core.generate_hatch_edges = lambda *a: []`, create a
`QApplication`, then instantiate every `TaskPanel*`.

**Visibility asserts**: use `isHidden()` or `isVisibleTo(parent)`. Plain `isVisible()` is always
False offscreen, so a test built on it passes for the wrong reason.

**Combo item-data comparisons**: PySide round-trips item data through a QVariant and rebuilds a NEW
dict on every `itemData()` call, so two reads of one item are never the same object. Compare with
`==`, never `is`.

## What the suite covers today

- `test_panneaux.py` — the broad one, and it earns its keep: constructs every argument-free panel,
  then walks the photo panel's 7 tramages **one at a time** (G-code produced, `M2` present, G64
  present, **no `G4` while the beam is on**, preview renders, note non-empty, verdict non-empty, and
  the *visible* settings are the ones that actually apply to that tramage). Three bugs shipped on
  29/07/2026 — an empty green tick, a defocus setting shown in a focus-only tramage, a tramage
  refusing because the panel's default feed didn't suit it — all had the same cause: nothing checked
  each tramage individually.
- `test_lignes_gravees.py` — the swelling-line tramage: measured width table, never sampling below
  the lowest measured power, the feed cliff, focus beating defocus on ratio, refusals.
- `test_contraste_pas.py` — the contrast verdict: it must move with the pitch, peak at
  `pitch = w_max`, name the optimum, and put **the feed before the pitch** when the feed is what's
  costing range.
- `test_micro_traits.py` — direction reversals inside a row, counted for **all 7** tramages,
  expecting zero. Written after the same bug shipped twice.

## `preparer()` BEFORE `import Part` — segfault with zero output

`preparer()` is what initialises FreeCAD's interpreter. A test importing `Part` at module level
*before* calling it dies on a bare **SEGFAULT**: no traceback, no message, and `lancer.py` prints an
`ÉCHEC` with an empty body — which looks like anything except an import-order problem. Cost a
bisection to find (2026-07-31, `test_fuseau.py`, the first test in the repo to need `Part` at module
level). Put `h = preparer()` first, then `import Part` / `import FreeCAD` below it.

## A test must not go red because the user MEASURED

The harness copies the **real** config, which is valuable — tests read the real nuancier and the
real kerf table. But several tests had quietly encoded the workshop's beech numbers *as of a
date*: "above F800 the trace no longer swells", "the fastest usable feed is F800".

On 2026-08-01 Christophe measured F1000–F3000 on a fresh board. `swell_max_feed` went from 800 to
3000 and **four tests fell at once**, with no line of code changed:
`test_lignes_gravees` (F1500 flat), `test_mire` (band 7 must slow down), `test_contraste_pas`,
`test_interpolation_mesures` (§5 assumed the grids were full).

A suite that reddens because the user does the one thing you keep asking them to do — measure — is
worse than no suite: it teaches you to ignore red.

`harness.figer_largeurs(core, materiau)` reinstalls a known focus table (`LARGEURS_REFERENCE`:
0.10→0.30 under F800, flat 0.10 at F1500/F3000) **in the throwaway copy**, keeping the defocus
table and the nuancier intact. Call it in any test whose property assumes a table *shape*. Tests
that check the workshop's data hangs together must deliberately NOT call it.

`figer_largeurs` also installs a canonical **defocus** table (`defocus=True`, the default): width
growing with height AND with power, always **below the optical spot**. Those are the properties
tests assume and the real measurements no longer guarantee — on 2026-08-01 the workshop's beech came
back at 3.35 mm at 55 mm of defocus and **3.27 at 60**, i.e. a *decrease* (2.4 %, inside the
measuring noise). `test_fuseau` fell on it. A test that assumes monotonicity must give itself
monotonic data.

A test that **counts** rows must own what it counts: `test_largeurs_libres` deletes a row and checks
the level is gone, which held only while defocus 60 had exactly one point — Planche 2b took it to
three. It now seeds its own material (and seeds it **off-grid**, since the free-width table displays
only what the fixed grid cannot).

Same idea for a property that needs a **complete** grid: build one in the test
(`test_interpolation_mesures` §5 now does) and, on the real grids, **count and print** rather than
assert — a divergence there is information about the measurements, not a defect in the code.

## `test_panneaux.py` sort explicitement en 0

It builds a dozen windows, each with grids, event filters and timers, and used to fail **at
random — about one run in four — with exit code 1 and no traceback**, every check printed OK. That
is not a test falling over: it is Qt/FreeCAD teardown handing back a non-zero code, with a widget
destruction order nobody here controls.

The file therefore drops its `_hote*` references, lets Qt digest, and calls `os._exit(0)` at the
very end. Every assertion runs **above** that line, so a real failure still raises and still exits
non-zero — verified by deliberately inserting `assert False` before the block. (First attempt put
the sabotage *after* `os._exit`, where it could never run; a check that cannot fail proves
nothing.)

A suite that reddens one run in four for no reason teaches you to ignore red, which is worse than
no suite at all.

## A stale `.pyc` can make a SABOTAGE look green (2026-08-04)

Python invalidates bytecode on the source's **mtime in whole seconds** and its **size**. A sabotage
that changes neither — `math.sin` → `math.cos` is byte-for-byte the same length — and is reverted
by `cp` **within the same second** leaves both unchanged, so the interpreter keeps running the
**cached** module. `inspect.getsource` still shows the correct source, which makes the diagnosis
maddening.

Reproduced deliberately: after that exact edit-and-revert, a healthy `laser_core.py` kept failing
`test_plume` §1 with the sabotaged result. The dangerous direction is the mirror image — a real
sabotage running against healthy cached bytecode, reported as harmless. **The whole protocol of
this repo rests on sabotages actually reddening.**

`tests/lancer.py` now purges every `__pycache__` under the repo before the first test
(`_purger_pyc`). When sabotaging by hand, outside the runner, purge it yourself:

```bash
find . -name __pycache__ -type d -exec rm -rf {} +
```

## Two rules for new tests here

1. **Test the property over the family, not the case that was reported.** A test written for the one
   generator just fixed would have stayed green through a month of the same bug living in its
   sibling.
2. **Verify against a really-generated file when one exists.** `/mnt/srv-partage/Gcode/*.ngc` holds
   what actually ran on the machine; counting a defect there is stronger than any argument. A
   headless test that only re-derives its own formula passes while still being wrong.

## `preparer()` forces S-direct — don't write machine files from it

`preparer()` calls `canal_puissance(core, m67=False)` so every test compares against one power
channel. That is right for tests, and `test_puissance_m67` covers the other channel across all
ten generator families (no `S` on a movement, well-formed `M67 E<n> Q<v>`, `M3`/`M5` kept).

But the workshop's config says `puissance_par_m67: true`, so a **file written for the machine**
from a harness-prepared `core` comes out in S-direct — one `S` word per block, which is the exact
thing two twin files proved stalls the PrintNC. On 2026-08-01 a control board generated this way
juddered on every power change; Christophe heard it before anything showed on screen, and his
first guess (the repeated `F200`) was the wrong word — a constant `F` costs nothing, the changing
`S` costs a full stop.

Call `core._apply_settings_config()` after `preparer()` whenever the output is going to be cut.

## Test the handler the user clicks, not the helpers around it

On 2026-08-01 the Grille de test's **Générer button was shipped broken**: it read
`self.spn_cell`, a widget that does not exist. Clicking it created the 3D objects, then raised
`AttributeError` before writing a single line of G-code. Christophe hit it on the first try.

The edit that should have fixed it had been written, but the script asserted on a *second* anchor,
that assert failed, and the file was **never written** — only the first "replacement done" message
was read. The syntax gate passed, because an unchanged file is still valid Python.

Worse, the verification written for it called `_deposer_fiche_grille` **directly**, stepping right
over the broken line. **The path that was tested was the path being written, not the path being
clicked.**

So: when a panel gains a feature, drive `_on_generer` (or whatever the button is wired to), with
`_write_gcode_with_dialog` monkeypatched to a temp file. That needs a real document
(`FreeCAD.newDocument`) — without one the handler refuses at its first line and the test passes
for the wrong reason.

Two things that surfaced on the way, both worth keeping:

- `hasattr(obj, "ViewObject")` is **true and useless** headless: the attribute exists and is
  `None`, so the next line dies on `None.LineColor`. Use
  `getattr(obj, "ViewObject", None) is not None` — fixed at all 8 sites, not just the one that
  bled.
- A test must not assert on a **persisted UI state**. `chk_mire.isChecked()` and the fold state of
  a section are whatever Christophe last left them; asserting on either goes red because he used
  the software. Assert that the widget *exists* and is in `_last_fields`; for fold state, clear the
  key first and set up the case the test actually means.

## `test_reglette.py` runs its checks in a **string**, not in the file

The file builds `SOUS_PROGRAMME = r'''…'''` and hands it to the *system* python (OpenCV is absent
from FreeCAD's). The driver below the string ends in `sys.exit`. Appending a new check to the end
of the file therefore puts it **after that exit**, in the wrong interpreter, where neither `np`
nor the module exist — and it never runs. On 2026-08-02 a check added that way passed without
executing a line.

That is the same shape as the `os._exit(0)` trap in `test_panneaux.py`: **a check that cannot run
proves nothing.** New checks go *inside* the string, before its closing quotes, and call the module
through `mod.` — the sub-program imports it as `mod`, not into its namespace.

## A synthetic fixture must be able to fail

The first version of §6 painted a hatched grid with a *perfect* 30 px pitch. Its regularity came
out at 1.00 — exactly the ruler's — so the fixture could not tell the two apart, and the check
passed under the broken code as happily as under the fixed one.

Real hatching bleeds and overlaps: on Christophe's board the cell rows scored **0.6–0.8** against
the ruler's **0.99–1.00**. The fixture now jitters the hatch spacing to reproduce that, and the
sabotage run yields **29.54 px/mm** — within half a pixel of the 29.01 the real board produced.

Always sabotage a new fixture before keeping it. If the deliberate break does not turn it red, the
fixture is decoration.

## Never touch the live FreeCAD session to test a behaviour

On 2026-08-02, verifying "create a document when none is open" was done by **closing Christophe's
documents in his running session**. One of them, `Nuancier_tons`, had never been saved. Its content
is gone.

The behaviour was verifiable without any of that: read the source, or drive a throwaway document.
`FreeCAD.closeDocument` in his session is the same class of act as writing to the workshop config —
it destroys something no computation can rebuild, and there is no undo.

**Rule: in the live session, read. Never close, never delete, never save-over.** Anything
destructive goes to a fresh document created for the purpose, or to the headless interpreter.

## A monotonicity check on measured data needs the measurement's own noise

`test_interpolation_mesures` §3 demanded a *perfect* decrease of darkness with feed. On the first
real tone board that turned red on **8.8 → 9.3** — half a point, on the one cell an old stray
engraving crossed. The wood's own grain spreads bare-wood readings over 6.4 points (σ 1.7), so
strict monotonicity is a demand the material cannot meet.

`TOLERANCE_GRAIN = 2.0` (one σ, rounded) comes from that measurement, not from taste. And the check
now proves it still **discriminates**: a synthetic 22-point jump — the real contradiction of that
morning — must be caught, a 0.5-point one must not, and the threshold must sit between the two.
Without that, raising the tolerance to 30 would have passed silently on data that has no defect.

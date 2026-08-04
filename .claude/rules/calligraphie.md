---
paths:
  - calligraphie.py
  - tests/test_calligraphie.py
---

# Calligraphie: skeleton, width, and the Z spindle

A calligraphic font is a **filled outline**. Engraving it as a line loses the very thing that
makes it calligraphy — the alternation of thick and thin. So the module extracts the **medial
axis** (what the pen travelled) plus the **local width**, and hands the width to
`laser_core.echelle_fuseau_z`: the head rises to widen the spot in the downstrokes and drops for
the hairlines. One pass, one gesture, nothing filled or gone over twice.

Written 2026-08-03 on Christophe's request, `.otf` files in hand.

## Fonts never enter the repo

`polices_disponibles()` scans the **user's** font folders; the panel takes a path. Commercial
script faces are almost all *personal use only* (both of the two he brought are), and this repo is
public under LGPL. The tests therefore work on a **synthetic** tapered stroke whose width is known
by construction, and touch a real file only where one is unavoidable.

A system font is not a fixture either: the first one found on the machine was **AdwaitaMono**, a
constant-weight monospace that never asks the Z to move. A check for "power follows width" passed
on it while proving nothing. Anything about the spindle is judged on the synthetic stroke.

## THE invariant: a chain never jumps

Every stage downstream — resampling, smoothing, the spindle, the G-code — interpolates between
consecutive points. **One jump becomes one engraved line**, silently, and the longer it is the more
visible.

The loop branch of `tracer` closed a chain onto its first pixel without checking it had come back:
a greedy walk that died in a dead end at the other end of the word got a straight segment across
all eighteen letters of "Atelier du Verdier" — and it was engraved. `_couper_aux_sauts` is now
applied at the exit of `tracer`, and `souder` fills its joins pixel by pixel so a weld cannot
reintroduce one. Overflow beyond the glyph: **11.3 % → 1.2 %**.

## A junction is not a corner: count transitions, not neighbours

`nombre_transitions` (the `A` of Zhang-Suen) is 1 at an end, 2 along a stroke, ≥3 at a real
junction. Counting 8-neighbours instead calls every staircase pixel of a diagonal a junction:
"Verdier" in Blacksword came out as **282 fragments, the longest 5.6 mm**, instead of ~130 gestures
whose longest is 31 mm. The preview came out dotted and the first hypothesis was that the Z could
not keep up.

`souder` then rejoins the chains that continue *straight* through a junction — a cursive crosses
its own strokes, and the fuseau needs **length** to lift the Z (`longueur_mini_fuseau`), so
chopping a stroke flattens its swell.

## Which measurement judges a stroke, and which one lies

**Σ width × length is not the area of the stroke.** A curving stroke overlaps itself and a junction
is counted once per branch, so that sum always overestimates. It reported "+40 % of ink" against
the real glyph — a defect that did not exist — and that phantom justified replacing the inscribed
disc with a **perpendicular chord**, which made overflow go from 4 % to 67 % (the path direction,
estimated on a rasterized skeleton, is wrong by 45° often enough that the ray runs *along* the
stroke and measures its length: 10 mm traces where the font asks 3.8).

What decides is the **raster sweep**: the disc walked along the path, compared pixel by pixel with
the glyph. Inscribed disc: 99 % of the glyph covered, 4 % overflow. Perpendicular chord: 52–67 %
overflow. Keep the distance transform.

The other half of the same lesson: measure fidelity against **what the font asks**, never against a
target already clipped by our own bounds — that flatters itself (0.02 mm of error announced while
the font was asking four times more).

## A repair that outlives its defect becomes the defect

`encre_oubliee` was written to serve **all** uncovered ink, because the medial axis stops half a
width short of a tapered tip and Christophe saw the result as "coupures dans les lettres". The
graph traversal (v2.65.0) closed those gaps at the source — and the repair kept firing. On "Atelier
du Verdier" at 120 mm, **27 of the 55 gestures were fills, and 24 of them landed inside a letter
already traced**: small strokes scattered along the junctions. Christophe highlighted them in
yellow: *"il faut juste le squelette de la lettre et bien sûr les points sur les i et accents"*.

Two rules replaced it, both judged on **ink**, never on a length:

* `taches_sans_geste` — fill only an ink component that **no gesture covers at all**. The criterion
  is coverage, not "the skeleton touches it": a detached dot does carry a one-or-two-pixel skeleton,
  too short to survive the traversal, so judging on the skeleton would call it served and leave it
  bare.
* `gestes_utiles` — drop a gesture whose footprint is already burnt by another. Longest first,
  cumulating. The threshold is read off the measurement, not chosen: contributions split into two
  heaps with a gap between them (0 % on one side, ≥10 % on the other), and 2 %, 5 % and 10 % remove
  **exactly the same set** on three fonts out of four. `APPORT_MINI = 0.05` sits mid-plateau.

La Graziela 55 → 25 gestures, Blacksword 142 → 36, for **0.01 point** of ink coverage; blunt
terminations 19 → 6. What is left bare is ~1000 slivers of ≤ 0.6 mm² along the tapered tips — an
i-dot is 7 mm², so nothing legible is lost.

Same trap in the same function: `longueur`, `w_min` and `w_max` were accumulated **inside the
building loop**, i.e. before pruning. A discarded stub could set the announced minimum width on its
own — the very number the panel uses to judge whether the material can make the stroke. They are now
recomputed over the final chains.

## A crossing is ONE node — thinning says two, and that cuts strokes in half

**An oblique crossing cannot produce a degree-4 node.** Thinning makes two degree-3 nodes joined by a
one- or two-pixel bridge, and a cursive is made of nothing else. `parcourir` pairs node by node, so
at each of the two it marries two branches out of three — nothing stops it stitching "left-bar +
bridge + lower-stem" and leaving the other two dangling. The stroke comes out **cut in its middle**.

The fixture that proves it is the simplest possible: **two bars in an X must engrave as two straight
strokes**, each corner to opposite corner. Before `fusionner_jonctions` they gave **four**, one of
them doubling back (`direction continuity = -0.00`) and two halves stopping dead at the centre.
Christophe, 04/08/2026, screenshot annotated 1-2-3 over an "A" and a "t": *"pour le t le 3e est coupé
en son centre, normalement on trace une ligne 1 puis 2 puis 3"*. He read the defect off the drawing
before any measurement.

`fusionner_jonctions` contracts a bridge whose two branch points sit inside the **same inscribed
disc** (gap ≤ the ink's radius there). It does not delete the bridge — it *appends* it to every branch
of the second node, so the chains stay continuous and no skeleton pixel is lost.

**The threshold needs its own fixture, and the X cannot provide it.** The X's bridge is two pixels;
removing the threshold changes nothing measurable there, so §13 passed under the broken code with the
threshold gone — it proved only half the rule. An **H** proves the other half: its crossbar is a
legitimate edge between two junctions, and swallowing it *duplicates* it into every branch. Total
gesture length against skeleton length: **1.00× with the threshold** (stable from k = 0.5 to 3.0),
**1.21× without**. Note the X sits at 1.40× at every threshold — both strokes must cross the centre —
so it is the H, not the X, that discriminates here.

## Two neighbouring junctions leave two ends nobody pairs

`parcourir` pairs branches **node by node**. Where two junctions touch — the rule at a cursive
crossing, thinning makes a little bridge between them — each leaves one branch dangling, and the two
free ends sit one or two pixels apart without ever seeing each other. (`fusionner_jonctions` removes
most of these at the source; `souder` catches what is left.)

That is not merely one gesture too many: the head lifts, transits, plunges and restarts **at the same
spot**. That half-millimetre is burnt **twice**, plus two stops, and it comes out as a black blob.
Fourteen such clusters among the fifty gesture ends of "Atelier du Verdier".

`souder` welds them under three conditions, in order: the gap fits within the **local ink width**
(proportional, so scale-invariant); the straight join lies **entirely inside the ink**; and the second
gesture continues the first rather than doubling back. The join is filled with its intermediate
pixels, so "a chain never jumps" still holds on the way out. It replaces `coudre`, which looked only
2 px around and had no ink guard.

**The ink guard needs a fixture that can fail.** On the ring-and-bar shape §2 used, removing the guard
changed nothing — every weld stayed inside the drawing anyway, so the check passed under the broken
code. An **open chevron** does discriminate: two ends continuing straight with background between
them, i.e. the straight-line-across-the-word disaster in miniature. Without the guard: 1 chain, 3 px
outside the ink. With it: 2 chains, none.

## Size is the only lever

The stroke width comes from the glyph scaled to the requested size, and the ceiling is the
material's widest **measured** burn. No power setting widens a trace past what the measured defocus
gives. So above a certain size the downstrokes are simply clipped, and the panel must say so **and
say by how much** — the verdict names the width that would fit. On the workshop's beech at F200
(0.18 → 3.43 mm), Blacksword tops out around 130 mm of text width; at 200 mm, 39 % of the trace is
out of reach.

## Higher means further from the wood

In this mode the spindle's `dz` *lifts* the head to widen the spot. Retracting to a global safe Z
between gestures, from a downstroke where the head already sits 47 mm up, is two Z round trips for
nothing — sixty times over. The emitter only lifts when the departure or arrival would drop below
the guard. Same family as the two wasted-travel defects Christophe caught **by ear** in the
halftones.

## Cost

~1 s for a word at `EM_PX = 600` (rendering + thinning + tracing). The panel caches on
(font, text, width) because the verdict recomputes on every keystroke.

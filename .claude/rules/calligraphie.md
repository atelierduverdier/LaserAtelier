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
applied at the exit of both `tracer` and `coudre` (the latter concatenates, so it inherits any jump
its halves carried). Overflow beyond the glyph: **11.3 % → 1.2 %**.

## A junction is not a corner: count transitions, not neighbours

`nombre_transitions` (the `A` of Zhang-Suen) is 1 at an end, 2 along a stroke, ≥3 at a real
junction. Counting 8-neighbours instead calls every staircase pixel of a diagonal a junction:
"Verdier" in Blacksword came out as **282 fragments, the longest 5.6 mm**, instead of ~130 gestures
whose longest is 31 mm. The preview came out dotted and the first hypothesis was that the Z could
not keep up.

`coudre` then rejoins the chains that continue *straight* through a junction — a cursive crosses
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

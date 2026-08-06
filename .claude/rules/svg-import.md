---
paths:
  - "svg_import.py"
---

# Native SVG import

Standalone SVG-to-geometry importer: parses a `.svg` directly (stdlib `xml.etree.ElementTree`, **no
Draft/DXF detour**) into one `Part::Feature` per top-level `<path>` element
(`Shape = Part.Compound(edges)`), matching the bare-edge-compound convention
`_faces_from_any_shape` / `chain_edges` already handle from Draft's own SVG/DXF import.

Why it exists: the DXF detour turned a real 23-`<path>` skull SVG into 210+ `Part::Feature`
fragments plus `_BlockDefinitions`/`Layer` plumbing. Native import gives 23 objects, individually
selectable.

## Layering — the reason it's testable

The path-grammar / Bezier-and-arc-flattening / transform / colour layer is **pure Python with zero
FreeCAD import at module level** — deliberately, so it's unit-testable with **no stubbing at all**.
Only the object-creation functions (`_subpath_to_edges`, `_record_to_object`, `import_svg_file`)
import `FreeCAD`/`Part`, locally inside themselves. Keep it that way when extending.

**No true OCCT Bezier/Arc edges anywhere** (matching the rest of the codebase): curves are flattened
to short `Part.LineSegment` chains.

## Flattening tolerance

`FLATTEN_TOL_MM = 0.02` is a max chord **DEVIATION (sagitta)**, not a point spacing — well under the
burn width, so no visible faceting even on large gentle curves. Since `chain_edges` re-densifies
segments at 0.3 mm spacing for G-code anyway, the finer import fidelity costs nothing downstream.

## Colour

`ViewObject.LineColor` from the path's resolved fill, inherited from ancestor `<g>`s per the normal
SVG cascade; `style=` beats `fill=`; `fill="none"` falls back to **that element's own** stroke, else
black. Use `LineColor`, not `ShapeColor` — these are edge-only shapes with no faces.

`ViewObject` guards must use `getattr(obj, 'ViewObject', None) is not None`: in `freecadcmd` the
attribute EXISTS but is None, so `hasattr` lets an AttributeError through.

## One recompute for the whole file

`doc.recompute()` runs **once, after the loop** — not per object. That is what makes it fast versus
the fragmented DXF detour, and it's the regression most likely to creep back in silently, so the
test suite asserts the call count explicitly.

## Parsing traps

- `_read_flag` must exist separately from `_read_number`: SVG packs an arc's `large-arc-flag` /
  `sweep-flag` as single characters with **no delimiter** against the next value, so `...,0,111.8`
  can mean `flag=1, flag=1, x=1.8`, not `x=111.8`. A generic float regex gets this wrong silently.
- Implicit command repeat is real (one `M` followed by several un-prefixed `c` groups) and present in
  actual marketplace SVGs.
- On `Z`/`z`, append `subpath_start` as an explicit point if not already coincident, and set
  `closed=True`. Not cosmetic: the `chain_edges`/hatch pipeline needs the chain to literally close
  within its own tolerance, or a closed SVG shape silently becomes un-hatchable later.
- A malformed `d` returns the subpaths that completed plus a warning — **never** crash the whole file
  over one bad `<path>`.
- No viewBox → scale `25.4/96` mm per user unit. viewBox but no width/height → same (the common case
  for this genre of file).

## Out of scope, announced not silent

`<use>`, gradients, `<clipPath>`/`<mask>`/`<filter>`, embedded raster `<image>`, and CSS
class-selector cascading. Each produces one collected `FreeCAD.Console.PrintWarning`, never a hard
failure.

## LightBurn files: convert, don't import (2026-08-06)

Christophe was sent a `.lbrn2` instead of an SVG. `outils/lbrn2_vers_svg.py` translates it;
`svg_import.py` then does what it already does well. **No 21st mode for an interchange format.**

The format, decoded on his 267-shape file — it is plain XML:

- `<Shape Type="Path">` carries `<XForm>` (an affine matrix, exactly SVG's `matrix()`),
  `<VertList>` (`V<x> <y>` then optional `c0x`/`c0y` outgoing and `c1x`/`c1y` incoming control
  points) and `<PrimList>` (`L<i> <j>` a segment, `B<i> <j>` a cubic).
- **An absent control point is written `c0x1` with no `c0y`.** The `1` is a marker, not a
  coordinate — keep a control point only when BOTH components are present.
- **`<PrimList>` is OPTIONAL**: 110 of his 267 paths have none, and the contour is then implicit
  (vertices in order, loop closed). Skipping them lost 41 % of the drawing.
- `Rx`/`Ry` on ellipses are CAPITALISED; looking for `rx` finds nothing.
- LightBurn works **Y up**, SVG Y down — everything is wrapped in a vertical mirror.

**The file carries its own PNG thumbnail** (`<Thumbnail Source="base64…">`), and that is what
verifies a conversion: rendering the produced SVG beside it showed the same clock face, numerals
and tick marks. Nothing else in the chain proves the geometry is right.

Layer colours are **deliberately NOT LightBurn's**: its palette wasn't read, so reproducing it
from memory would be a fabricated table. Hues are spread by the golden ratio (a 0.137 step put
layers 2, 9 and 10 in the same green), one `<g id="calque_N">` per `CutIndex`, and
`resolve_fill_color`'s stroke fallback carries the colour onto each imported object.


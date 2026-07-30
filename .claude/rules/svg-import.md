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

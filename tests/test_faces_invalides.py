# -*- coding: utf-8 -*-
"""Une face invalide ne doit pas graver blanc en silence.

Trouvé à l'AUDIT du 06/08/2026, pas à l'usage. `Part.Face([contour, trou])`
sans orienter le trou rend une face d'aire 400,196 mm² là où 399,804 était
attendu — le trou s'AJOUTE au lieu de se soustraire — et `isValid()` répond
False. Le hachurage l'acceptait pourtant et rendait **1 seul segment de
0,5 mm** pour une pièce de 20 × 20 mm : gravure quasi blanche, sans un mot.

C'était atteignable : les faces d'un objet sélectionné étaient renvoyées
TELLES QUELLES, d'où qu'elles viennent (autre atelier, macro, import). Le
constructeur de l'atelier oriente correctement — il n'était simplement pas
consulté quand la forme portait déjà des faces.

LA TESSELLATION NE DÉMASQUE PAS CE CAS, et c'est le piège du piège : cette
face se tessellise très bien (124 triangles). C'est `isValid()` qui parle
— et seulement sur les faces VENUES DU DEHORS, jamais sur celles que
l'atelier vient de bâtir (une face sur fils tangents peut rester invalide
sans gêner, cf. `_faces_rapides_depuis_fils`).
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402

doc = FreeCAD.newDocument("faces_invalides")

CONTOUR = Part.makePolygon([FreeCAD.Vector(x, y, 0) for x, y in
                            [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]])
TROU = Part.Wire(Part.makeCircle(0.25, FreeCAD.Vector(10, 10, 0)).Edges)


class _Sel:
    def __init__(self, obj):
        self.Object = obj
        self.SubElementNames = tuple()
        self.HasSubObjects = False
        self.Document = obj.Document
        self.SubObjects = tuple()
        self.ObjectName = obj.Name


def pose(nom, forme):
    o = doc.addObject("Part::Feature", nom)
    o.Shape = forme
    doc.recompute()
    return o


print("=" * 62)
print("§1  La pièce d'essai est BIEN cassée (sinon on ne prouve rien)")
print("=" * 62)

mauvaise = Part.Face([CONTOUR, TROU])
print("   aire %.3f mm² (une face saine : 399.804), valide=%s, tessell.=%d"
      % (mauvaise.Area, mauvaise.isValid(), len(mauvaise.tessellate(0.05)[1])))
assert not mauvaise.isValid(), "la pièce d'essai n'est pas invalide"
assert mauvaise.Area > 400.0, (
    "le trou ne s'ajoute pas : la pièce d'essai ne reproduit rien")
assert len(mauvaise.tessellate(0.05)[1]) > 0, (
    "elle ne se tessellise pas — le piège du piège disparaîtrait, et un "
    "contrôle par tessellation suffirait")

print()
print("=" * 62)
print("§2  Elle est REBÂTIE, et le hachurage retrouve la pièce entière")
print("=" * 62)

obj = pose("Invalide", mauvaise)
faces = core.get_faces_from_selection_for_hatch([_Sel(obj)]) or []
aire = sum(f.Area for f in faces)
aretes = core.generate_hatch_edges(faces, 0.3, 45.0) or []
longueur = sum(e.Length for e in aretes)
print("   %d face(s), aire %.3f mm² | %d hachures, %.1f mm de trait"
      % (len(faces), aire, len(aretes), longueur))
assert abs(aire - 399.804) < 0.5, (
    "aire %.3f : la face n'a pas été rebâtie (le trou s'ajoute encore)" % aire)
assert len(aretes) > 50, (
    "%d hachure(s) : la gravure sortirait quasi blanche — c'était 1 avant "
    "le correctif" % len(aretes))
assert longueur > 1000.0, "%.1f mm de trait pour 20 x 20 mm" % longueur

print()
print("=" * 62)
print("§3  Une face SAINE n'est pas touchée")
print("=" * 62)

saine = Part.Face(Part.makePolygon(
    [FreeCAD.Vector(x, y, 0) for x, y in
     [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]))
obj2 = pose("Saine", saine)
faces2 = core.get_faces_from_selection_for_hatch([_Sel(obj2)]) or []
print("   %d face(s), aire %.1f mm² (attendu 100.0)"
      % (len(faces2), sum(f.Area for f in faces2)))
assert len(faces2) == 1 and abs(faces2[0].Area - 100.0) < 1e-6, (
    "une face saine a été modifiée : %r" % [f.Area for f in faces2])

print()
print("=" * 62)
print("§4  Ce que l'atelier bâtit lui-même n'est PAS jugé sur isValid")
print("=" * 62)

# `_faces_rapides_depuis_fils` produit parfois des faces invalides sur des
# fils tangents, sans que ça gêne : les juger ici les rejetterait à tort.
compound = Part.Compound(list(CONTOUR.Edges) + list(TROU.Edges))
faces3 = core._faces_from_any_shape(compound, "aretes") or []
print("   depuis des ARÊTES : %d face(s), aire %.3f"
      % (len(faces3), sum(f.Area for f in faces3)))
assert faces3, "le chemin par les arêtes ne rend plus rien"
assert abs(sum(f.Area for f in faces3) - 399.804) < 0.5

FreeCAD.closeDocument("faces_invalides")
print()
print("TOUT EST VERT")

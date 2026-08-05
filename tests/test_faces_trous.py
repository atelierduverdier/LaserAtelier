# -*- coding: utf-8 -*-
"""Faces à trous qui SE CHEVAUCHENT.

Un dessin au trait importé en SVG n'est pas fait de trous bien rangés :
ce sont des rubans posés les uns sur les autres, et deux rubans qui se
croisent donnent deux trous qui se chevauchent. `Part.Face([contour] +
[trous])` sort alors invalide et MUETTE À LA TESSELLATION, donc
impossible à hachurer.

Le chemin rapide abandonnait tout le lot à Bullseye, qui rend le contour
SANS ses trous. Mesuré sur la pin-up Ricard de Christophe (05/08/2026) :
23 965 mm2 d'encre au lieu de 6 801, dont une face de 22 796 mm2 couvrant
la silhouette entière -- « le remplissage se fait mal ».

La propriété tenue ici : une face dont les trous se chevauchent doit
rendre l'aire du contour MOINS L'UNION des trous, et se hachurer.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import Part                                                   # noqa: E402
import FreeCAD                                                # noqa: E402


def carre(x0, y0, x1, y1):
    """Fil carré fermé, sens direct."""
    p = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return Part.makePolygon([FreeCAD.Vector(x, y, 0.0) for x, y in p])


# Contour 100 x 100 ; deux trous de 40 x 40 qui se recouvrent sur 20 x 20.
CONTOUR = carre(0, 0, 100, 100)
TROU_A = carre(20, 20, 60, 60)
TROU_B = carre(40, 40, 80, 80)
UNION_TROUS = 1600.0 + 1600.0 - 400.0                  # 2800
AIRE_ATTENDUE = 10000.0 - UNION_TROUS                  # 7200

print("=" * 62)
print("§1  La pièce d'essai reproduit bien la panne")
print("=" * 62)

# Les trous doivent être posés en sens INVERSE, comme le fait le code.
def inverse(fil):
    pts = [v.Point for v in fil.Vertexes]
    return Part.makePolygon(list(reversed(pts)) + [pts[-1]])


brute = Part.Face([CONTOUR, inverse(TROU_A), inverse(TROU_B)])
tess = len(brute.tessellate(0.05)[1])
print("   Part.Face(contour + 2 trous chevauchants) : "
      "valide=%s, aire %.1f, triangles %d" % (brute.isValid(), brute.Area, tess))
assert tess == 0, (
    "la pièce d'essai ne reproduit RIEN : cette face se tessellise déjà, "
    "donc le test passerait aussi sous le code fautif")
print("   -> muette à la tessellation : la panne est bien reproduite")

print()
print("=" * 62)
print("§2  Le chemin rapide rend des faces, et la BONNE aire")
print("=" * 62)

faces = core._faces_rapides_depuis_fils([CONTOUR, TROU_A, TROU_B])
assert faces, ("le chemin rapide a rendu None : il repasse la main à "
               "Bullseye, qui rendra le contour SANS ses trous")
aire = sum(f.Area for f in faces)
print("   %d face(s), aire %.1f mm2 (attendu %.1f)" % (len(faces), aire, AIRE_ATTENDUE))
assert abs(aire - AIRE_ATTENDUE) < 0.5, (
    "aire %.1f au lieu de %.1f : %s" % (
        aire, AIRE_ATTENDUE,
        "les trous ont été perdus" if aire > 9000 else
        "le recouvrement est soustrait DEUX fois"))

# Le piège que la mesure a révélé : soustraire les deux trous du modèle
# polygonal compte le recouvrement deux fois (6 800 au lieu de 7 200).
naif = 10000.0 - 1600.0 - 1600.0
assert abs(aire - naif) > 1.0, (
    "l'aire vaut la soustraction naïve %.1f : le recouvrement de 400 mm2 "
    "est compté deux fois" % naif)
print("   -> ni contour nu (10 000) ni double soustraction (%.0f)" % naif)

print()
print("=" * 62)
print("§3  Ces faces se hachurent réellement")
print("=" * 62)

aretes = core.generate_hatch_edges(faces, 2.0, 0.0) or []
print("   hachures au pas 2 mm : %d arêtes" % len(aretes))
assert len(aretes) > 10, "faces inhachurables : le remplissage sortirait vide"

# Aucune hachure ne doit traverser l'union des trous.
dedans = 0
for e in aretes:
    for v in e.Vertexes:
        x, y = v.Point.x, v.Point.y
        if (20 < x < 60 and 20 < y < 60) or (40 < x < 80 and 40 < y < 80):
            dedans += 1
print("   extrémités de hachure tombées DANS un trou : %d" % dedans)
assert dedans == 0, "le hachurage traverse les trous"

print()
print("=" * 62)
print("§4  Le lot entier n'est pas sacrifié pour une face")
print("=" * 62)

# Une face saine à côté de la face malade : les deux doivent sortir.
LOIN = carre(200, 0, 240, 40)
faces2 = core._faces_rapides_depuis_fils([CONTOUR, TROU_A, TROU_B, LOIN])
assert faces2, "le lot mixte a été abandonné en bloc"
aire2 = sum(f.Area for f in faces2)
print("   lot mixte : %d faces, aire %.1f (attendu %.1f)"
      % (len(faces2), aire2, AIRE_ATTENDUE + 1600.0))
assert abs(aire2 - (AIRE_ATTENDUE + 1600.0)) < 0.5

print()
print("TOUT EST VERT")

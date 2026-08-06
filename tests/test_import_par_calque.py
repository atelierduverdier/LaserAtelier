# -*- coding: utf-8 -*-
"""L'import range les tracés par calque, ou à défaut par couleur.

Christophe, 06/08/2026 : « si dans le fichier SVG ou LightBurn il y a des
couleurs, pourrais-tu importer les objets dans des dossiers séparés par
couleur ? là j'ai une longue liste d'objets ». Son fichier LightBurn en
produit **267** : l'arbre devient illisible, et rien ne dit ce qui va
ensemble.

Le CALQUE d'abord — il porte l'intention du dessinateur, et un fichier
LightBurn traduit le nomme (`calque_9`) —, la COULEUR ensuite, seule
séparation disponible sur un SVG quelconque.

Et RIEN quand il n'y a qu'un lot : un dossier unique serait un clic de
plus pour retrouver exactement la même liste.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import os                                                     # noqa: E402
import tempfile                                               # noqa: E402
import FreeCAD                                                # noqa: E402
import svg_import                                             # noqa: E402

DOSSIER = tempfile.mkdtemp(prefix="import-calques-")


def ecrire(nom, contenu):
    chemin = os.path.join(DOSSIER, nom)
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(contenu)
    return chemin


def carre(x, y, c=6):
    return "M{0} {1}L{2} {1}L{2} {3}L{0} {3}Z".format(x, y, x + c, y + c)


def groupes(doc):
    return sorted((o.Label, len(o.Group)) for o in doc.Objects
                  if o.TypeId == "App::DocumentObjectGroup")


print("=" * 62)
print("§1  Un SVG à calques nommés : un dossier par calque")
print("=" * 62)

svg_calques = ecrire("calques.svg", """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <g id="calque_9" stroke="#1f77b4" fill="none">
    <path stroke="#1f77b4" d="{a}"/><path stroke="#1f77b4" d="{b}"/>
  </g>
  <g id="calque_2" stroke="#d62728" fill="none">
    <path stroke="#d62728" d="{c}"/>
  </g>
</svg>""".format(a=carre(0, 0), b=carre(10, 0), c=carre(20, 0)))

doc = FreeCAD.newDocument("calques")
n, _av = svg_import.import_svg_file(svg_calques)
print("   %d objets -> %s" % (n, groupes(doc)))
assert n == 3, "%d objets importés au lieu de 3" % n
assert groupes(doc) == [("Calque 2", 1), ("Calque 9", 2)], (
    "les calques ne sont pas repris : %s" % groupes(doc))
racine = [o for o in doc.Objects
          if o.TypeId != "App::DocumentObjectGroup" and not o.InList]
assert not racine, "%d objets restés à la racine" % len(racine)
FreeCAD.closeDocument("calques")

print()
print("=" * 62)
print("§2  Sans calque nommé, c'est la COULEUR qui range")
print("=" * 62)

svg_couleurs = ecrire("couleurs.svg", """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path stroke="#FF0000" fill="none" d="{a}"/>
  <path stroke="#FF0000" fill="none" d="{b}"/>
  <path stroke="#0000FF" fill="none" d="{c}"/>
</svg>""".format(a=carre(0, 0), b=carre(10, 0), c=carre(20, 0)))

doc = FreeCAD.newDocument("couleurs")
n, _av = svg_import.import_svg_file(svg_couleurs)
print("   %d objets -> %s" % (n, groupes(doc)))
assert groupes(doc) == [("Couleur #0000FF", 1), ("Couleur #FF0000", 2)], (
    "le rangement par couleur ne marche pas : %s" % groupes(doc))
FreeCAD.closeDocument("couleurs")

print()
print("=" * 62)
print("§3  Un seul lot : AUCUN dossier")
print("=" * 62)

svg_uni = ecrire("uni.svg", """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path stroke="#000000" fill="none" d="{a}"/>
  <path stroke="#000000" fill="none" d="{b}"/>
</svg>""".format(a=carre(0, 0), b=carre(10, 0)))

doc = FreeCAD.newDocument("uni")
n, _av = svg_import.import_svg_file(svg_uni)
print("   %d objets -> %s" % (n, groupes(doc) or "aucun dossier"))
assert n == 2, "%d objets" % n
assert not groupes(doc), (
    "un dossier a été créé pour un seul lot : c'est un clic de plus pour "
    "retrouver la même liste (%s)" % groupes(doc))
FreeCAD.closeDocument("uni")

print()
print("=" * 62)
print("§4  Le rangement ne PERD ni ne DUPLIQUE aucun tracé")
print("=" * 62)

doc = FreeCAD.newDocument("integrite")
n, _av = svg_import.import_svg_file(svg_calques)
ranges = []
for g in doc.Objects:
    if g.TypeId == "App::DocumentObjectGroup":
        ranges.extend(o.Name for o in g.Group)
print("   %d importés, %d rangés, %d distincts"
      % (n, len(ranges), len(set(ranges))))
assert len(ranges) == n, "%d rangés pour %d importés" % (len(ranges), n)
assert len(set(ranges)) == n, "un objet apparaît dans deux dossiers"
FreeCAD.closeDocument("integrite")

print()
print("TOUT EST VERT")

# -*- coding: utf-8 -*-
"""Un dessin au trait ne se hachure pas — et l'atelier doit le DIRE.

Christophe, 06/08/2026 : « les hachures sur ma forme ne se font pas, mais
cela doit être dû aux épaisseurs de traits ». C'était exactement ça, et
son dessin le chiffre : 96 faces de **0,104 mm** de large en médiane (la
plus large 0,745), pour 272 mm² d'encre. Au pas d'1 mm, **96 faces sur
96** sont plus fines que le pas.

Le hachurage ne rend pas zéro — il rend pire : 561 segments de **0,25 mm
de long en médiane**, espacés d'un pas ENTIER le long de rubans larges
d'un dixième de millimètre. Il pointille le trait. Et la longueur de
segment ne bouge pas quand on resserre le pas (0,251 mm à pas 1,0 ;
0,253 à pas 0,08) : ce sont des traversées, pas des remplissages.

Ce qui noircit ces rubans, c'est le CONTOUR : ses deux lignes sont
distantes de 0,104 mm et la brûlure mesurée sur le hêtre fait 0,12 à
0,20 mm — elles se rejoignent. 1 738 mm de contour contre 3 401 mm de
hachures au pas 0,08 pour le même noir.

Le programme le savait déjà (`inset_face_robuste` saute les traits fins
« le contour les noircit ») mais en silence, et Christophe a cherché une
soirée. D'où ce verdict.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
core = h.core
tp = h.tp
sans_dialogues()

import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402
from PySide6 import QtWidgets                                 # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
doc = FreeCAD.newDocument("dessin_au_trait")


def ruban(x0, largeur, longueur):
    """Une bande fine, comme un trait de dessin."""
    return Part.Face(Part.makePolygon([
        FreeCAD.Vector(x, y, 0) for x, y in
        [(x0, 0), (x0 + largeur, 0), (x0 + largeur, longueur),
         (x0, longueur), (x0, 0)]]))


print("=" * 62)
print("§1  La mesure de largeur dit la VRAIE largeur")
print("=" * 62)

# 2 x aire / perimetre est exact pour une bande longue : c'est ce qui rend
# le chiffre affiché crédible, et donc utilisable.
for larg_vraie in (0.10, 0.25, 1.00):
    f = ruban(0.0, larg_vraie, 20.0)
    mesuree = core.largeurs_typiques_faces([f])[0]
    ecart = abs(mesuree - larg_vraie) / larg_vraie
    print("   ruban de %.2f mm -> mesuré %.4f mm (écart %.1f %%)"
          % (larg_vraie, mesuree, 100 * ecart))
    assert ecart < 0.06, "mesure fausse de %.1f %%" % (100 * ecart)

print()
print("=" * 62)
print("§2  Un dessin au trait est reconnu, un aplat ne l'est pas")
print("=" * 62)

trait = [ruban(i * 3.0, 0.10, 20.0) for i in range(12)]
aplat = [ruban(0.0, 25.0, 25.0)]

milieu, fines, total = core.dessin_au_trait(trait, 1.0)
print("   12 rubans de 0,10 mm, pas 1,00 : %d/%d plus fines, médiane %.3f mm"
      % (fines, total, milieu))
assert fines == total, "les rubans fins ne sont pas repérés"

milieu_a, fines_a, total_a = core.dessin_au_trait(aplat, 1.0)
print("   un aplat de 25 mm, pas 1,00   : %d/%d plus fines, médiane %.1f mm"
      % (fines_a, total_a, milieu_a))
assert fines_a == 0, "un aplat est pris pour un dessin au trait"

# Et le seuil se déplace avec le pas : à 0,05 mm le hachurage mord.
_m, fines_fin, _t = core.dessin_au_trait(trait, 0.05)
print("   les mêmes rubans au pas 0,05  : %d/%d plus fines" % (fines_fin, total))
assert fines_fin == 0, "au pas 0,05 mm un ruban de 0,10 n'est plus 'trop fin'"

print()
print("=" * 62)
print("§3  Le panneau le DIT, et se tait quand il n'y a rien à dire")
print("=" * 62)

panneau = tp.TaskPanelFilledEngraving([])
assert hasattr(panneau, "lbl_finesse"), "le verdict de finesse a disparu"

# On sème les faces là où le panneau les lit, puis on appelle ce que le
# panneau appelle lui-même à chaque changement de réglage.
tp._MEMO_REMPLISSAGE["faces"] = trait
panneau._maj_finesse(1.0, 0.12)
visible = not panneau.lbl_finesse.isHidden()
texte = panneau.lbl_finesse.text()
print("   dessin au trait, pas 1,00, brûlure 0,12 : %s"
      % ("PARLE" if visible else "muet"))
print("   « %s »" % texte[:96])
assert visible, "le panneau reste muet sur un dessin qu'il ne peut pas hachurer"
assert "0.10" in texte or "0,10" in texte, "la largeur mesurée n'est pas dite"
# La brûlure couvre le ruban : le message doit nommer le CONTOUR, sinon il
# décrit un problème sans donner l'issue.
assert "CONTOUR" in texte.upper(), (
    "le message ne dit pas que le contour suffit : il laisse l'utilisateur "
    "chercher, ce qui est exactement ce qui s'est passé")

tp._MEMO_REMPLISSAGE["faces"] = aplat
panneau._maj_finesse(1.0, 0.12)
print("   aplat de 25 mm                          : %s"
      % ("PARLE" if not panneau.lbl_finesse.isHidden() else "muet"))
assert panneau.lbl_finesse.isHidden(), (
    "verdict affiché sur un aplat : un avertissement permanent ne se lit plus")

print()
print("=" * 62)
print("§4  Quand la brûlure NE couvre PAS, le message change d'issue")
print("=" * 62)

# Rubans de 0,60 mm : trop fins pour un pas d'1 mm, trop larges pour être
# noircis par un trait brûlé de 0,12. L'issue n'est plus le contour.
gros = [ruban(i * 3.0, 0.60, 20.0) for i in range(12)]
tp._MEMO_REMPLISSAGE["faces"] = gros
panneau._maj_finesse(1.0, 0.12)
texte2 = panneau.lbl_finesse.text()
print("   rubans 0,60 mm, brûlure 0,12 : « %s »" % texte2[-88:])
assert not panneau.lbl_finesse.isHidden()
assert "CONTOUR" not in texte2.upper() or "pas plus fin" in texte2, (
    "le message conseille le contour alors que la brûlure ne couvre pas "
    "le ruban : %r" % texte2)
assert "pas plus fin" in texte2, "aucune issue proposée : %r" % texte2

FreeCAD.closeDocument("dessin_au_trait")
print()
print("TOUT EST VERT")

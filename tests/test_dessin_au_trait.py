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

CORRIGÉ LE JOUR MÊME, et c'est la leçon principale de ce fichier : la
première version raisonnait sur la MÉDIANE des largeurs et concluait « le
contour seul suffit ». Trois rendus côte à côte l'ont démentie — hachures
seules au pas 1 mm : des tirets épars ; contour seul : un dessin au trait
propre ; contour + hachures fines : le noir massif qu'il cherchait. La
mesure a suivi : médiane 0,104 mm, mais **97,4 % de l'aire** vit dans des
rubans de 0,12 mm ou plus, et DEUX faces en portent 85 %. La médiane
décrit le nombre de faces, pas la surface qu'on veut noire. Le verdict
pèse désormais par l'AIRE (§5 gèle exactement ce piège).
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

a = core.analyse_finesse(trait, 1.0, 0.12)
print("   12 rubans de 0,10 mm, pas 1,00 : %.0f %% de l'aire pointillée"
      % (100 * a["part_pointee"]))
assert a["part_pointee"] > 0.99, "les rubans fins ne sont pas repérés"

b = core.analyse_finesse(aplat, 1.0, 0.12)
print("   un aplat de 25 mm, pas 1,00   : %.0f %% pointillée"
      % (100 * b["part_pointee"]))
assert b["part_pointee"] == 0, "un aplat est pris pour un dessin au trait"

# Et le seuil se déplace avec le pas : à 0,05 mm le hachurage mord.
c = core.analyse_finesse(trait, 0.05, 0.12)
print("   les mêmes rubans au pas 0,05  : %.0f %% pointillée"
      % (100 * c["part_pointee"]))
assert c["part_pointee"] == 0, "au pas 0,05 mm un ruban de 0,10 n'est plus traversé"

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
assert "%" in texte, "la part d'encre concernée n'est pas dite"
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
assert "Descends vers" in texte2, "aucun pas conseillé : %r" % texte2

print()
print("=" * 62)
print("§5  L'AIRE décide, pas le nombre de faces")
print("=" * 62)

# LE PIÈGE, gelé ici. Un dessin au trait compte des dizaines de rubans
# minuscules et quelques formes qui portent tout le noir. Sur la pin-up de
# Christophe : médiane 0,104 mm, mais 97,4 % de l'aire dans des rubans
# >= 0,12 mm, dont 85 % dans DEUX faces. Raisonner sur la médiane conseille
# « le contour suffit » ; l'image dit le contraire.
melange = ([ruban(i * 1.0, 0.04, 4.0) for i in range(40)]      # 40 broutilles
           + [ruban(60.0, 0.35, 60.0), ruban(70.0, 0.35, 60.0)])  # 2 vraies masses
larg = core.largeurs_typiques_faces(melange)
mediane = larg[len(larg) // 2]
a5 = core.analyse_finesse(melange, 1.0, 0.12)
part_grosses = 100.0 * (1.0 - a5["part_contour"])
print("   %d faces, médiane %.3f mm -- mais %.0f %% de l'aire est HORS "
      "de portée du contour" % (len(melange), mediane, part_grosses))
assert mediane < 0.12, "la médiane devrait être minuscule (c'est le piège)"
assert a5["part_contour"] < 0.5, (
    "le contour est crédité de %.0f %% de l'aire : le verdict compte les "
    "faces au lieu de peser l'encre" % (100 * a5["part_contour"]))

tp._MEMO_REMPLISSAGE["faces"] = melange
panneau._maj_finesse(1.0, 0.12)
texte5 = panneau.lbl_finesse.text()
print("   « %s »" % texte5[:110])
assert not panneau.lbl_finesse.isHidden()
assert "Descends vers" in texte5, (
    "le verdict conseille le contour sur un dessin dont l'encre est dans "
    "les grosses formes -- exactement le contresens de la première "
    "version : %r" % texte5)
conseil = a5["pas_utile"] / 2.0
print("   pas conseillé : %.2f mm (les masses font %.2f mm)"
      % (conseil, 0.35))
assert conseil < 0.35, "le pas conseillé ne mord pas dans les masses"

FreeCAD.closeDocument("dessin_au_trait")
print()
print("TOUT EST VERT")

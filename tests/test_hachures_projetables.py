# -*- coding: utf-8 -*-
"""Un aplat doit pouvoir atteindre une surface 3D.

Christophe, 06/08/2026 : « il y a un souci sur la projection de surface
remplie sur une surface 3d, ça ne fonctionne pas ». Sa session, lue en
lecture seule, donne la réponse sans ambiguïté : son « Motif_Projete »
porte 10 564 arêtes, et projeter « MotifSVG001 » (10 491 arêtes) en rend
exactement 10 564 — alors que projeter l'aperçu de remplissage en
rendrait 10 521. Il avait donc projeté le CONTOUR seul, et le Marquage
gravait un pourtour.

Ce n'était pas une erreur de sa part : **Gravure remplie calcule ses
hachures et les envoie droit dans le G-code**. Rien n'atterrissait dans
le document, donc il n'y avait rien à projeter. Le refus du mode sur une
forme galbée lui conseillait pourtant de « projeter le résultat » — un
geste que seul Hachures 2D permettait.

D'où le bouton « Déposer les hachures dans le document ». Le contour, lui,
n'en a pas besoin : c'est la forme d'origine, déjà projetable.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
core = h.core
tp = h.tp
dialogues = sans_dialogues()

import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402
import FreeCADGui as Gui                                      # noqa: E402
from PySide6 import QtWidgets                                 # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

doc = FreeCAD.newDocument("hachures_projetables")

# Un motif plat : un carré avec un trou, pour que le remplissage ait une
# forme à respecter.
exterieur = Part.makePolygon([FreeCAD.Vector(x, y, 0) for x, y in
                              [(0, 0), (40, 0), (40, 30), (0, 30), (0, 0)]])
trou = Part.makePolygon([FreeCAD.Vector(x, y, 0) for x, y in
                         [(12, 10), (28, 10), (28, 20), (12, 20), (12, 10)]])
motif = doc.addObject("Part::Feature", "Motif")
motif.Shape = Part.Compound(list(exterieur.Edges) + list(trou.Edges))

# Une surface 3D VRAIMENT COURBE : un cylindre couché. Un pavé incliné ne
# ferait pas l'affaire -- une projection sur un plan penché reste PLANE, et
# `forme_est_plane` a raison de le dire (mesuré : 0,0000 mm d'écart). C'est
# la courbure, pas l'inclinaison, qui met le remplissage en défaut.
socle = doc.addObject("Part::Feature", "Socle")
cyl = Part.makeCylinder(40, 80, FreeCAD.Vector(-10, -25, -20),
                        FreeCAD.Vector(0, 1, 0))
socle.Shape = cyl
doc.recompute()


class _SelEx:
    def __init__(self, obj):
        self.Object = obj
        self.SubElementNames = tuple()
        self.ObjectName = obj.Name
        self.HasSubObjects = False
        self.Document = obj.Document
        self.SubObjects = tuple()
        self.FullName = obj.Name


Gui.Selection.clearSelection = lambda *a, **k: None
Gui.Selection.getSelectionEx = lambda *a, **k: [_SelEx(motif)]
Gui.Selection.getSelection = lambda *a, **k: [motif]

print("=" * 62)
print("§1  Le bouton EXISTE et dépose vraiment un objet")
print("=" * 62)

panneau = tp.TaskPanelFilledEngraving([_SelEx(motif)])
assert hasattr(panneau, "btn_deposer_hachures"), (
    "le bouton de dépôt a disparu : sans lui, aucun aplat ne peut "
    "atteindre une surface 3D")

avant = set(o.Name for o in doc.Objects)
del dialogues[:]
# ON PILOTE LE BOUTON, pas la fonction d'à côté : c'est le chemin que
# Christophe clique, et c'est là que les défauts se logent.
panneau.btn_deposer_hachures.click()
app.processEvents()
nouveaux = [o for o in doc.Objects if o.Name not in avant]
print("   objets créés : %s" % [o.Label for o in nouveaux])
assert nouveaux, "le clic n'a rien déposé (dialogues : %s)" % dialogues
depose = nouveaux[0]
aretes = list(depose.Shape.Edges)
print("   « %s » : %d traits" % (depose.Label, len(aretes)))
assert len(aretes) > 10, "trop peu de traits pour un remplissage : %d" % len(aretes)

print()
print("=" * 62)
print("§2  Ce dépôt est PLAT, donc acceptable comme motif à projeter")
print("=" * 62)

ecart = core.ecart_au_plan(depose.Shape)
print("   écart au plan : %.4f mm (tolérance %.3f)"
      % (ecart, core.ECART_PLAN_MAXI_MM))
assert core.forme_est_plane(depose.Shape), "le dépôt n'est pas plan"

motifs, reference = core.split_projection_selection(
    [_SelEx(depose), _SelEx(socle)])
print("   classement pour la projection : %d motif(s), surface = %s"
      % (len(motifs or []), getattr(reference, "Label", None)))
assert motifs and reference is socle, (
    "la projection refuse ce dépôt : %r / %r" % (motifs, reference))

print()
print("=" * 62)
print("§3  Et la projection le drape bien sur le relief")
print("=" * 62)

projete = core.drop_edges_to_surface(aretes, socle.Shape)
assert projete, "la projection n'a rien rendu"
zs = [v.Point.z for e in projete for v in e.Vertexes]
print("   %d traits projetés, Z de %.2f à %.2f mm"
      % (len(projete), min(zs), max(zs)))
assert max(zs) - min(zs) > 0.5, (
    "les traits projetés sont tous à la même hauteur (%.3f mm d'écart) : "
    "ils n'épousent pas la surface" % (max(zs) - min(zs)))

print()
print("=" * 62)
print("§4  Le refus sur une forme galbée nomme le bon geste")
print("=" * 62)

# C'est la moitié du défaut : le message conseillait de « projeter le
# résultat », geste impossible sans le dépôt.
galbe = doc.addObject("Part::Feature", "MotifGalbe")
galbe.Shape = Part.Compound([e for e in projete])
doc.recompute()
assert not core.forme_est_plane(galbe.Shape), "la pièce d'essai est plane"

del dialogues[:]
panneau2 = tp.TaskPanelFilledEngraving([_SelEx(galbe)])
panneau2._build_edges()
textes = " ".join(t for _g, _t, t in dialogues)
print("   message : %s" % textes[:120].replace("\n", " "))
assert textes, "aucun refus : une forme galbée est acceptée en silence"
assert "Déposer les hachures" in textes, (
    "le refus ne nomme pas le dépôt : il conseille un geste que ce mode "
    "ne permet pas")
# ET il doit parler D'ABORD à celui qui est déjà arrivé au bout : une forme
# galbée est presque toujours une projection, donc quelqu'un qui en est à la
# dernière étape. Lui réciter les quatre depuis le début se lit comme un
# reproche -- c'est ce qui est arrivé le 06/08/2026, hachures déposées et
# projetées, panneau ouvert au mauvais endroit.
assert "Marquage de motif" in textes, (
    "le refus ne nomme pas le mode qui grave une projection")
assert "job combiné" in textes, (
    "le refus ne dit pas où ajouter la projection au job combiné, alors "
    "que c'est précisément ce que l'utilisateur cherchait")
i_marquage = textes.index("Marquage de motif")
i_etapes = textes.index("1. sélectionne")
assert i_marquage < i_etapes, (
    "les quatre étapes passent AVANT le conseil qui sert à celui qui est "
    "déjà arrivé au bout")

FreeCAD.closeDocument("hachures_projetables")
print()
print("TOUT EST VERT")

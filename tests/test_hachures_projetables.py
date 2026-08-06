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

D'OÙ LE BOUTON, ET SA SIMPLIFICATION LE MÊME JOUR. Première version : il
déposait les seules hachures, au motif que le contour est la forme
d'origine, déjà projetable. Christophe a refait la manœuvre trois fois et
a conclu : « en résumé je n'y comprends rien, il faut simplifier la
procédure ». Sa logique était pourtant juste — remplir, sélectionner le
motif et le Pad, projeter, marquer — mais elle butait sur un fait que
rien n'annonce : LE REMPLISSAGE N'EST PAS UN OBJET. Ce qu'il projetait
était la forme d'origine, donc son seul contour.

Le dépôt contient désormais LES HACHURES ET LE CONTOUR : l'objet posé EST
la gravure. Et le bouton enchaîne la projection quand une seule surface
3D est présente, pour que trois gestes n'en fassent qu'un.
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
assert "surface 3D" in panneau.btn_deposer_hachures.text(), (
    "le bouton ne dit pas à quoi il sert : %r"
    % panneau.btn_deposer_hachures.text())

avant = set(o.Name for o in doc.Objects)
del dialogues[:]
# ON PILOTE LE BOUTON, pas la fonction d'à côté : c'est le chemin que
# Christophe clique, et c'est là que les défauts se logent.
panneau.btn_deposer_hachures.click()
app.processEvents()
nouveaux = [o for o in doc.Objects if o.Name not in avant]
print("   objets créés : %s" % [o.Label for o in nouveaux])
assert nouveaux, "le clic n'a rien déposé (dialogues : %s)" % dialogues
depose = [o for o in nouveaux if o.Name.startswith("Remplissage")][0]
aretes = list(depose.Shape.Edges)
print("   « %s » : %d traits" % (depose.Label, len(aretes)))
assert len(aretes) > 10, "trop peu de traits pour un remplissage : %d" % len(aretes)

# LE DÉPÔT DOIT CONTENIR LE CONTOUR AUSSI. C'est ce manque qui a fait dire
# trois fois « j'ai juste le contour » : l'objet posé doit ÊTRE la gravure.
#
# Le compte est EXACT, pas « plus grand que ». Première version de ce
# contrôle : « plus d'arêtes que le contour » -- vrai avec les hachures
# seules (256 contre 8), donc incapable de voir la différence. Un contrôle
# qui ne peut pas échouer ne prouve rien.
_fill, _contour, _d, _cz = panneau._build_edges(silent=True)
contour_attendu = len(_contour or [])
attendu = len(_fill or []) + contour_attendu
print("   %d hachures + %d contour = %d attendu ; déposé : %d"
      % (len(_fill or []), contour_attendu, attendu, len(aretes)))
assert contour_attendu > 0, "la pièce d'essai n'a pas de contour à vérifier"
assert len(aretes) == attendu, (
    "le dépôt ne contient pas hachures ET contour : %d arêtes déposées "
    "pour %d attendues" % (len(aretes), attendu))

print()
print("=" * 62)
print("§1bis  Le même clic PROJETTE, sans rien redemander")
print("=" * 62)

# La simplification demandée : trois gestes n'en font plus qu'un. Quand une
# seule surface 3D est présente, le bouton propose de projeter et le fait.
projetes = [o for o in nouveaux if o.Name.startswith("Motif_Projete")]
print("   objets projetés créés par le clic : %s" % [o.Label for o in projetes])
assert projetes, (
    "le clic n'a pas enchaîné la projection alors qu'UNE seule surface 3D "
    "est présente : l'utilisateur doit tout refaire à la main")
resultat = projetes[0]
zs = [v.Point.z for e in resultat.Shape.Edges for v in e.Vertexes]
print("   « %s » : %d arêtes, Z de %.2f à %.2f mm"
      % (resultat.Label, len(resultat.Shape.Edges), min(zs), max(zs)))
assert max(zs) - min(zs) > 0.5, "la projection n'épouse pas le relief"
assert len(resultat.Shape.Edges) > contour_attendu, (
    "la projection ne porte que le contour : %d arêtes" % len(resultat.Shape.Edges))

# Et le dernier mot doit dire QUOI FAIRE ENSUITE, sinon on repart chercher.
dits = " ".join(x for _g, _t, x in dialogues)
assert "Marquage de motif" in dits, (
    "rien ne dit avec quel mode graver la projection : %r" % dits[-160:])
print("   le message final nomme « Marquage de motif » : ✓")

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
assert "Projeter ce remplissage" in textes, (
    "le refus ne nomme pas le bouton qui dépose : il conseille un geste "
    "que ce mode ne permet pas")
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

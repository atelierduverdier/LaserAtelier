# -*- coding: utf-8 -*-
"""La surface 3D à sonder se trouve toute seule.

Christophe, 06/08/2026 : « au lieu de sélectionner le Pad ET
Motif_Projete, le même système que pour la projection : une boîte
déroulante, ou s'il n'y en a qu'un le prendre par défaut ».

DEUX DES TROIS TEMPS EXISTAIENT DÉJÀ, en silence. Lu dans sa session :
son « Motif_Projete » portait bien `LaserAtelierSurfaceRef` pointant sur
son Corps, et `split_selection` retrouvait la surface avec le SEUL motif
sélectionné. Il sélectionnait les deux depuis des jours parce que rien ne
le lui disait — et le message d'après-projection le lui conseillait même
explicitement, à tort.

L'ordre retenu :
  1. un solide EXPLICITEMENT sélectionné gagne — c'est un choix ;
  2. sinon celui mémorisé sur le motif projeté ;
  3. sinon le seul solide du document, ou on demande lequel.
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
doc = FreeCAD.newDocument("surface_sondee")

motif = doc.addObject("Part::Feature", "MotifPose")
motif.Shape = Part.Compound(list(Part.makePolygon(
    [FreeCAD.Vector(x, y, 3) for x, y in
     [(0, 0), (20, 0), (20, 15), (0, 15), (0, 0)]]).Edges))
socle = doc.addObject("Part::Feature", "Socle")
socle.Shape = Part.makeBox(40, 30, 10, FreeCAD.Vector(-5, -5, -10))
doc.recompute()


class _Sel:
    def __init__(self, obj):
        self.Object = obj
        self.SubElementNames = tuple()
        self.ObjectName = obj.Name
        self.HasSubObjects = False
        self.Document = obj.Document
        self.SubObjects = tuple()
        self.FullName = obj.Name


print("=" * 62)
print("§1  Un solide sélectionné gagne toujours")
print("=" * 62)

_ar, ref = tp._aretes_et_surface([_Sel(motif), _Sel(socle)])
print("   motif + socle : surface trouvée = %s" % (ref is not None))
assert ref is not None, "un solide explicitement sélectionné doit être pris"

print()
print("=" * 62)
print("§2  Le SEUL motif suffit quand la surface est mémorisée")
print("=" * 62)

# C'est ce que `run_projection` écrit sur le motif projeté.
motif.addProperty("App::PropertyLink", "LaserAtelierSurfaceRef",
                  "LaserAtelier", "")
motif.LaserAtelierSurfaceRef = socle
doc.recompute()

_ar, ref2 = tp._aretes_et_surface([_Sel(motif)])
print("   motif seul (surface mémorisée) : trouvée = %s" % (ref2 is not None))
assert ref2 is not None, (
    "la surface mémorisée sur le motif n'est pas retrouvée : l'utilisateur "
    "doit resélectionner le solide à chaque fois")

print()
print("=" * 62)
print("§3  Sans mémoire, le SEUL solide du document est pris")
print("=" * 62)

nu = doc.addObject("Part::Feature", "MotifNu")
nu.Shape = Part.Compound(list(motif.Shape.Edges))
doc.recompute()

_ar, ref3 = tp._aretes_et_surface([_Sel(nu)])
print("   motif sans mémoire, 1 solide : trouvée = %s" % (ref3 is not None))
assert ref3 is not None, (
    "un seul solide dans le document et il n'est pas pris : c'est "
    "exactement le geste qu'on voulait retirer")

print()
print("=" * 62)
print("§4  Plusieurs solides : on DEMANDE, le plus recouvrant en tête")
print("=" * 62)

# `sans_dialogues` répond la PREMIÈRE entrée proposée : c'est donc l'ordre
# de la liste qui décide, et il doit mettre en tête le solide sous le motif.
#
# LE SOLIDE LOINTAIN EST CRÉÉ EN PREMIER, ET C'EST TOUT L'INTÉRÊT. Première
# version de cette section : le bon socle existait déjà avant, donc il
# arrivait en tête par simple ordre de création et le tri ne changeait
# rien -- sabotage du classement, test toujours vert. Un contrôle qui ne
# peut pas échouer ne prouve rien. On recrée donc le bon socle APRÈS le
# mauvais : sans classement, c'est le lointain qui serait proposé.
loin = doc.addObject("Part::Feature", "SocleLoin")
loin.Shape = Part.makeBox(20, 20, 10, FreeCAD.Vector(500, 500, 0))
forme_socle = socle.Shape.copy()
doc.removeObject(socle.Name)
socle = doc.addObject("Part::Feature", "SocleProche")
socle.Shape = forme_socle
doc.recompute()
assert [o.Name for o in tp._solides_du_document()].index("SocleLoin") == 0, (
    "le solide lointain n'est pas en tête de l'ordre du document : la "
    "pièce d'essai ne peut pas voir la différence")

sous = tp._recouvrement_xy(nu.Shape, socle.Shape)
ailleurs = tp._recouvrement_xy(nu.Shape, loin.Shape)
print("   « %s » recouvre %.0f %% | « %s » recouvre %.0f %%"
      % (socle.Label, 100 * sous, loin.Label, 100 * ailleurs))
assert sous > ailleurs, "le classement proposerait le mauvais solide"

_ar, ref4 = tp._aretes_et_surface([_Sel(nu)])
assert ref4 is not None, "aucune surface retenue après la question"
choisi = ref4.BoundBox
print("   retenu : boîte X %.0f..%.0f (le socle est en %.0f..%.0f)"
      % (choisi.XMin, choisi.XMax,
         socle.Shape.BoundBox.XMin, socle.Shape.BoundBox.XMax))
assert abs(choisi.XMin - socle.Shape.BoundBox.XMin) < 1e-6, (
    "c'est le solide LOINTAIN qui a été proposé en premier : la sonde est "
    "un raycast vertical, il ne peut rien recevoir")

print()
print("=" * 62)
print("§5  Le panneau DIT d'où vient la surface")
print("=" * 62)


class _Panneau:
    pass


# §4 a supprimé puis recréé le socle : le lien mémorisé pointait sur un
# objet disparu. On le rétablit, sinon on mesurerait la branche « choisie »
# en croyant mesurer la branche « mémorisée ».
motif.LaserAtelierSurfaceRef = socle
doc.recompute()

p = _Panneau()
tp._aretes_et_surface([_Sel(motif)], p)
print("   origine annoncée : %r" % p._origine_reference)
assert p._origine_reference, (
    "rien n'est retenu sur l'origine : c'est ce silence qui a fait "
    "sélectionner le solide en trop pendant des jours")
assert "mémoris" in p._origine_reference, (
    "l'origine ne dit pas que la surface venait du motif : %r"
    % p._origine_reference)

print()
print("=" * 62)
print("§6  Plus aucun texte ne réclame les DEUX objets")
print("=" * 62)

# Le mécanisme était en place, et trois textes continuaient d'enseigner
# l'ancien geste : l'avertissement de la commande, son infobulle, et le
# mode d'emploi du panneau. Christophe les a suivis -- « il m'a dit que je
# devais sélectionner la forme aussi. Je veux le menu ». Un correctif que
# la documentation contredit n'est pas livré.
import io as _io
_fautifs = []
for _nom in ("commands.py", "task_panels.py"):
    _src = _io.open("/home/christophe/.local/share/FreeCAD/v1-1/Mod/"
                    "LaserAtelier/" + _nom, encoding="utf-8").read()
    for _motif in ("TOUS LES DEUX EN MÊME TEMPS",
                   "les deux en même temps",
                   "les deux ensemble"):
        if _motif in _src:
            _fautifs.append("%s : %r" % (_nom, _motif))
print("   textes réclamant encore les deux objets : %s" % (_fautifs or "aucun"))
assert not _fautifs, (
    "ces textes enseignent encore l'ancien geste alors que la surface se "
    "trouve seule : %s" % ", ".join(_fautifs))

FreeCAD.closeDocument("surface_sondee")
print()
print("TOUT EST VERT")
